#! /usr/bin/env python3

import argparse
import email
import glob
import openai
import os
import random
import re
import sys

from collections import OrderedDict

def thread_to_string(thread):
  s=""
  for e in thread:
    s += f"{e}"
  return s

def random_thread(emails):
  random_key, random_value = random.choice(list(emails.items()))
  return random_value

def analyze_thread(thread_string):

  openai.api_key = os.getenv("OPENAI_API_KEY")
  model="gpt-3.5-turbo",
  model='gpt-4'

  response = openai.ChatCompletion.create(
    model="gpt-3.5-turbo",
    messages=[
      {
        "role": "system",
        "content": "You will be provided with an email thread to a mailing list dedicated to the Lustre parallel file system. Please respond in JSON. Use the following fields. Summary: one-sentence summary. Replies: The number of replies. Category: Single-word classification of this email. Tone: single-word classification of the emotional tone of the email thread. Answered: true or false whether the initial question was answered. Elapsed: number of days before an answer was reached."
      },
      {
        "role": "user",
        "content": thread_string
      }
    ],
    temperature=0.5,
    max_tokens=256,
    top_p=1,
    frequency_penalty=0,
    presence_penalty=0
  )

  return response

# the pipermail download tool has a specific naming convention for the downloaded files.
# use that convention to sort them by time
def piper_sort(filename):
    match = re.search(r'(\d{4})-(\w+).txt', filename)
    if match:
        year, month = match.groups()
        month_order = [
            'January', 'February', 'March', 'April', 'May', 'June',
            'July', 'August', 'September', 'October', 'November', 'December'
        ]
        return int(year), month_order.index(month)
    else:
      print(f"Error: Attempting to analyze a file {filename} which does not appear to hold pipermail")
      sys.exit(255)

def parse_archive(archive):
  # we should have used https://codeberg.org/alinur/pipermail-listfetch.git to fetch an archive
  # therefore we can make assumptions about the file naming here

  filename_pattern = f"{archive}/[1-9][0-9][0-9][0-9]-[A-Z][a-z]*.txt"
  matching_files = glob.glob(filename_pattern)

  email_threads = OrderedDict()

  email_delimiter_pattern = r'From +([\w\.\-\+]+) +at +([\w\.\-]+) +([\w\s\d:]+)'

  # can use these just for debugging
  counts = { k:0 for k in ('new', 'replies', 'unmatched' ) }

  sorted_filenames = sorted(matching_files, key=piper_sort)
  for file in sorted_filenames:
    print(file)

    cur_email = None
    with open(file, "r") as f:
      for line in f:
        new_email = re.search(email_delimiter_pattern,line)
        if new_email:
          if cur_email:
            # actually parse the email here
            msg = email.message_from_string(cur_email)
            orig = msg['References']
            if orig: 
              orig = orig.split()[0]
              try:
                email_threads[orig].append(msg)
                counts['replies'] += 1
              except KeyError:
                print(f"Warn: Email with references {orig} does not match any existing emails.")
                email_threads[orig] = [msg,]
                counts['unmatched'] += 1
                #print(sorted(all_messages.keys()))
                #sys.exit(255)
            else:
              email_threads[msg['Message-ID']] = [msg,]
              counts['new'] += 1
          cur_email = line
        else:
          try:
            cur_email += line
          except:
            print(f"We seem to be missing an email delimiter in {line}")
            sys.exit(255)
          if line.startswith('From '):
            print(f"Warn: Did we miss a delimiter in {file}:{line}?")
    
  print(counts)
  return email_threads


def parse_args():
  parser = argparse.ArgumentParser(description="""
      Mailing List Analyzer
      """,
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument('-v', '--verbose',      help='More verbse output', action='store_true', default=False)
  parser.add_argument('ARCHIVE', help='Folder where a mailing list archive has been copied')
  args = parser.parse_args()

  return args

def main(args):
  args = parse_args()

  if not os.path.isdir(args.ARCHIVE):
    print(f"Error: {args.ARCHIVE} is not a directory holding a mailing list archive")
    sys.exit(255)

  threads = parse_archive(args.ARCHIVE)

  # now let's get a random email thread and ask chatgpt to analyze it
  thread = thread_to_string(random_thread(threads))
  print(thread)
  response = analyze_thread(thread)
  print(f"{response}")


# call main function if executed directly
if __name__ == '__main__':
  main(sys.argv[1:])
