<?xml version="1.0" ?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output omit-xml-declaration="yes" indent="yes"/>
  
  <!-- Copy the whole XML document -->
  <xsl:template match="node()|@*">
     <xsl:copy>
       <xsl:apply-templates select="node()|@*"/>
     </xsl:copy>
  </xsl:template>

  <!-- Replace <target dev='hdd'...> with <target dev='sda'...> for CD-ROM -->
  <xsl:template match="/domain/devices/disk[@device='cdrom']/target/@dev">
    <xsl:attribute name="dev">
      <xsl:value-of select="'sda'"/>
    </xsl:attribute>
  </xsl:template>

  <!-- Replace <target bus='ide'...> with <target bus='sata'...> for CD-ROM -->
  <xsl:template match="/domain/devices/disk[@device='cdrom']/target/@bus">
    <xsl:attribute name="bus">
      <xsl:value-of select="'sata'"/>
    </xsl:attribute>
  </xsl:template>
  
  <!-- Remove <alias> element for CD-ROM -->
  <xsl:template match="/domain/devices/disk[@device='cdrom']/alias" />

  <!-- Add serial numbers to extra disks -->
  <xsl:template match="/domain/devices/disk[source and target][not(target/@dev='vda')]">
    <xsl:copy>
      <xsl:apply-templates select="@*|node()"/>
      <serial>
        <xsl:value-of select="concat('lustre-mds00.', substring(target/@dev, 3, 1))"/>
      </serial>
    </xsl:copy>
  </xsl:template>

</xsl:stylesheet>
