"""Shared units, statistics, PostScript layout, topology and PDF output."""
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import tempfile
import textwrap

GIB = 2 ** 30
TOPOLOGY_TEMPLATE = Path(__file__).resolve().parent.parent / 'templates/report_topology.dot.j2'

def stats(values):
    if not values:
        return None
    lo, hi = min(values.values()), max(values.values())
    avg = statistics.mean(values.values())
    return {'count': len(values), 'mean': avg, 'stddev_population': statistics.pstdev(values.values()),
            'min': lo, 'min_nodes': sorted(k for k, v in values.items() if v == lo),
            'max': hi, 'max_nodes': sorted(k for k, v in values.items() if v == hi),
            'coefficient_of_variation': statistics.pstdev(values.values()) / avg if avg else None,
            'per_node': values}

def ps_string(text):
    return str(text).encode('ascii', 'replace').decode().replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


class Pages:
    """Small PostScript layout adapter for the already-installed PDF toolchain."""
    width, height = 612, 792
    def __init__(self, default_subtitle="TESSI / COMPONENT PERFORMANCE", footer="Measured component baselines | storage + InfiniBand"):
        self.default_subtitle = default_subtitle
        self.footer = footer
        self.ops = ['%!PS-Adobe-3.0', '<< /PageSize [612 792] >> setpagedevice']
        self.number = 0
        self.y = 700
        self.open = False
    def text(self, x, y, text, size=10, bold=False, color=(.15, .22, .29)):
        self.ops.append(f'{color[0]} {color[1]} {color[2]} setrgbcolor /Helvetica{"-Bold" if bold else ""} findfont {size} scalefont setfont {x} {y} moveto ({ps_string(text)}) show')
    def line(self, x, y, x2, y2, color=(.78, .83, .87)):
        self.ops.append(f'{color[0]} {color[1]} {color[2]} setrgbcolor 0.6 setlinewidth newpath {x} {y} moveto {x2} {y2} lineto stroke')
    def rect(self, x, y, width, height, color):
        self.ops.append(f'{color[0]} {color[1]} {color[2]} setrgbcolor {x} {y} {width} {height} rectfill')
    def page(self, title, subtitle=None):
        if self.open:
            self.ops.append('showpage')
        self.open = True
        self.number += 1
        self.text(42, 750, subtitle or self.default_subtitle, 9, True, (.18, .44, .55))
        self.text(42, 718, title, 23, True)
        self.line(42, 701, 570, 701)
        self.text(42, 25, self.footer, 8)
        self.text(550, 25, str(self.number), 8)
        self.y = 675
    def paragraph(self, text, width=94, size=10):
        for line in textwrap.wrap(str(text), width=width):
            if self.y < 55:
                self.page('Method and interpretation (continued)')
            self.text(42, self.y, line, size)
            self.y -= size + 5
        self.y -= 8
    def kv(self, key, value):
        lines = textwrap.wrap(str(value), width=65) or ['-']
        if self.y - len(lines)*14 < 55:
            self.page('Details (continued)')
        self.text(42, self.y, key, 10, True)
        for line in lines:
            self.text(210, self.y, line, 9)
            self.y -= 14
        self.y -= 8
    def embed_eps(self, eps, x, y, width, height):
        bbox = re.search(r'^%%BoundingBox: ([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)', eps, re.M)
        if not bbox:
            raise ValueError('Graphviz EPS lacks BoundingBox')
        x0, y0, x1, y1 = map(float, bbox.groups())
        scale = min(width / (x1-x0), height / (y1-y0))
        tx, ty = x + (width-(x1-x0)*scale)/2, y + (height-(y1-y0)*scale)/2
        self.ops += ['gsave', 'save /showpage {} def',
                     f'{tx} {ty} translate {scale} {scale} scale {-x0} {-y0} translate',
                     '%%BeginDocument: topology.eps', eps, '%%EndDocument', 'restore', 'grestore']
    def finish(self):
        return '\n'.join(self.ops + ['showpage', '%%EOF']) + '\n'


def short_name(host, data):
    alias = host.split('.')[0]
    physical = data['hosts'][host]['fqdn'].split('.')[0]
    return f'{alias} ({physical})' if alias != physical else alias


def format_bw(value):
    return 'unavailable' if value is None else f'{value/GIB:,.3f} GiB/s'


def format_iops(value):
    return 'unavailable' if value is None else f'{value:,.0f} ops/s'

def atomic_json(path, value):
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name + '-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def render_topology(data, directory, template=TOPOLOGY_TEMPLATE):
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    directory.mkdir(parents=True, exist_ok=True)
    env = Environment(loader=FileSystemLoader(str(template.parent)), undefined=StrictUndefined)
    dot = directory / 'topology.dot'
    dot.write_text(env.get_template(template.name).render(manifest=data))
    eps = directory / 'topology.eps'
    for fmt, output in [('eps', eps), ('png', directory / 'topology.png')]:
        subprocess.run(['dot', '-T' + fmt, str(dot), '-o', str(output)], check=True, timeout=60)
    return eps.read_text()


def write_pdf(postscript, directory, stem, output_pdf):
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / (stem + '.ps')
    source.write_text(postscript)
    generated = directory / (stem + '.pdf')
    temporary = directory / (stem + '.tmp.pdf')
    subprocess.run(['ps2pdf', '-dAutoRotatePages=/None', str(source), str(temporary)], check=True, timeout=60)
    os.replace(temporary, generated)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    if output_pdf.resolve() != generated.resolve():
        shutil.copyfile(generated, output_pdf)
    return generated
