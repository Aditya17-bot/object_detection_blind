"""A minimal OOXML (.docx) writer.

No dependencies: a .docx is a zip of XML parts, and the subset needed for a
two-column conference paper is small. Written rather than pulled in because
python-docx is not installed here and this machine has no pandoc, no Word and
no LibreOffice to convert with.

Supports what the paper needs and nothing else: a one-column title block
followed by a two-column body, headings, justified body text, inline runs with
bold/italic/monospace, images sized in inches, booktabs-style tables, block
quotes, and a numbered reference list.

Units: OOXML measures in twips (1/20 pt, so 1 inch = 1440) and images in EMU
(1 inch = 914400).
"""

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

TWIP = 1440          # per inch
EMU = 914400         # per inch

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="png" ContentType="image/png"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

APP_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
<Application>BlindAssist paper/docx_writer.py</Application>
</Properties>"""


def _core_xml(title, author):
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>{escape(title)}</dc:title><dc:creator>{escape(author)}</dc:creator>
<cp:lastModifiedBy>{escape(author)}</cp:lastModifiedBy>
</cp:coreProperties>"""


class Docx:
    """Builds a document body, then writes the package."""

    def __init__(self, body_font="Times New Roman", body_size=9.0,
                 title="", author=""):
        self.font = body_font
        self.size = body_size
        self.title = title
        self.author = author
        self.parts = []          # xml fragments, in order
        self.images = []         # (name, bytes)

    # -- low level ---------------------------------------------------------

    def _rpr(self, bold=False, italic=False, size=None, font=None,
             color=None, caps=False, spacing=None):
        size = size or self.size
        bits = [f'<w:rFonts w:ascii="{font or self.font}" '
                f'w:hAnsi="{font or self.font}" w:cs="{font or self.font}"/>']
        if bold:
            bits.append("<w:b/>")
        if italic:
            bits.append("<w:i/>")
        if caps:
            bits.append("<w:smallCaps/>")
        if color:
            bits.append(f'<w:color w:val="{color}"/>')
        if spacing:
            bits.append(f'<w:spacing w:val="{spacing}"/>')
        bits.append(f'<w:sz w:val="{int(size * 2)}"/>')
        bits.append(f'<w:szCs w:val="{int(size * 2)}"/>')
        return "<w:rPr>" + "".join(bits) + "</w:rPr>"

    def _run(self, text, **kw):
        return (f"<w:r>{self._rpr(**kw)}"
                f'<w:t xml:space="preserve">{escape(text)}</w:t></w:r>')

    def runs(self, pieces):
        """pieces: list of (text, kwargs) or plain strings."""
        out = []
        for piece in pieces:
            if isinstance(piece, str):
                out.append(self._run(piece))
            else:
                text, kw = piece
                out.append(self._run(text, **kw))
        return "".join(out)

    def _ppr(self, align=None, before=0, after=0, line=None, indent=None,
             keep_next=False, border_top=False, border_bottom=False,
             hanging=None):
        bits = []
        if keep_next:
            bits.append("<w:keepNext/>")
        if border_top or border_bottom:
            edges = ""
            if border_top:
                edges += '<w:top w:val="single" w:sz="8" w:space="1" w:color="000000"/>'
            if border_bottom:
                edges += '<w:bottom w:val="single" w:sz="8" w:space="1" w:color="000000"/>'
            bits.append(f"<w:pBdr>{edges}</w:pBdr>")
        spacing = f'<w:spacing w:before="{int(before)}" w:after="{int(after)}"'
        if line:
            spacing += f' w:line="{int(line)}" w:lineRule="auto"'
        spacing += "/>"
        bits.append(spacing)
        if indent is not None or hanging is not None:
            ind = "<w:ind"
            if indent is not None:
                ind += f' w:firstLine="{int(indent)}"'
            if hanging is not None:
                ind += f' w:left="{int(hanging)}" w:hanging="{int(hanging)}"'
            ind += "/>"
            bits.append(ind)
        if align:
            bits.append(f'<w:jc w:val="{align}"/>')
        return "<w:pPr>" + "".join(bits) + "</w:pPr>"

    # -- public building blocks -------------------------------------------

    def para(self, content, **ppr):
        if isinstance(content, str):
            content = self._run(content)
        elif isinstance(content, list):
            content = self.runs(content)
        self.parts.append(f"<w:p>{self._ppr(**ppr)}{content}</w:p>")

    def title_block(self, title, subtitle):
        self.para([(title, dict(size=17, bold=True))],
                  align="center", after=60)
        if subtitle:
            self.para([(subtitle, dict(size=11.5))], align="center", after=150)

    def author_grid(self, authors, per_row=2, width_in=7.0):
        """ACM lays authors out side by side rather than in one stacked list.
        A borderless table is the only way to get columns inside a section that
        is itself single-column.

        authors: list of (name, [affiliation lines], email or None).
        """
        col = width_in / per_row
        rows = [authors[i:i + per_row] for i in range(0, len(authors), per_row)]
        grid = "".join(f'<w:gridCol w:w="{int(col * TWIP)}"/>'
                       for _ in range(per_row))
        xml = ['<w:tbl><w:tblPr><w:tblLayout w:type="fixed"/>'
               '<w:tblCellMar>'
               '<w:top w:w="0" w:type="dxa"/><w:left w:w="60" w:type="dxa"/>'
               '<w:bottom w:w="0" w:type="dxa"/><w:right w:w="60" w:type="dxa"/>'
               "</w:tblCellMar></w:tblPr>",
               f"<w:tblGrid>{grid}</w:tblGrid>"]
        for row in rows:
            cells = []
            for index in range(per_row):
                body = ""
                if index < len(row):
                    name, lines, email = row[index]
                    body = (f"<w:p>{self._ppr(align='center', after=20)}"
                            f"{self._run(name, size=10.5)}</w:p>")
                    for line in lines:
                        body += (f"<w:p>{self._ppr(align='center', after=18)}"
                                 f"{self._run(line, size=8.5)}</w:p>")
                    if email:
                        body += (f"<w:p>{self._ppr(align='center', after=18)}"
                                 f"{self._run(email, size=8.5)}</w:p>")
                    # trailing pad so a cell with an email does not butt up
                    # against the name in the row below it
                    body += f"<w:p>{self._ppr(after=0)}{self._run('', size=5)}</w:p>"
                else:
                    body = f"<w:p>{self._ppr(align='center')}</w:p>"
                cells.append(
                    f'<w:tc><w:tcPr><w:tcW w:w="{int(col * TWIP)}" '
                    'w:type="dxa"/></w:tcPr>' + body + "</w:tc>")
            xml.append(f"<w:tr>{''.join(cells)}</w:tr>")
        xml.append("</w:tbl>")
        self.parts.append("".join(xml))
        self.para("", after=80)

    def heading(self, number, text):
        label = f"{number}  {text}" if number else text
        self.para([(label.upper(), dict(bold=True, size=9.5))],
                  before=170, after=60, keep_next=True)

    def subheading(self, text):
        self.para([(text, dict(bold=True, italic=True))],
                  before=110, after=40, keep_next=True)

    def body(self, content, first=False):
        self.para(content, align="both", line=216,
                  indent=0 if first else 0.14 * TWIP)

    def block_quote(self, content):
        self.para(content, align="both", line=216, before=60, after=60,
                  hanging=0.16 * TWIP)

    def image(self, name, data, width_in, height_in):
        self.images.append((name, data))
        index = len(self.images)
        cx, cy = int(width_in * EMU), int(height_in * EMU)
        drawing = (
            f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
            f'<wp:extent cx="{cx}" cy="{cy}"/>'
            f'<wp:docPr id="{index}" name="Figure {index}"/>'
            f"<a:graphic><a:graphicData "
            f'uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f"<pic:pic><pic:nvPicPr>"
            f'<pic:cNvPr id="{index}" name="{escape(name)}"/><pic:cNvPicPr/>'
            f"</pic:nvPicPr>"
            f'<pic:blipFill><a:blip r:embed="rIdImg{index}"/>'
            f"<a:stretch><a:fillRect/></a:stretch></pic:blipFill>"
            f"<pic:spPr><a:xfrm><a:off x=\"0\" y=\"0\"/>"
            f'<a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
            f"</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>")
        # NOT via para(): that escapes a str argument, which turns the drawing
        # markup into visible angle brackets in the document.
        self.parts.append(
            f"<w:p>{self._ppr(align='center', before=90, after=40)}"
            f"{drawing}</w:p>")

    def caption(self, label, text):
        self.para([(label, dict(bold=True, size=8)),
                   (" " + text, dict(size=8))],
                  align="both", after=110, line=200)

    def table(self, rows, widths_in, header_rows=1, size=8.0, aligns=None):
        """booktabs look: rule above, rule under the header, rule at the foot."""
        aligns = aligns or ["left"] + ["right"] * (len(widths_in) - 1)
        grid = "".join(f'<w:gridCol w:w="{int(w * TWIP)}"/>' for w in widths_in)
        xml = ['<w:tbl><w:tblPr>'
               '<w:tblLayout w:type="fixed"/>'
               # CT_TblCellMar is an ordered sequence: top, left, bottom,
               # right. Word tolerates other orders; strict validators do not.
               '<w:tblCellMar>'
               '<w:top w:w="18" w:type="dxa"/><w:left w:w="40" w:type="dxa"/>'
               '<w:bottom w:w="18" w:type="dxa"/><w:right w:w="40" w:type="dxa"/>'
               "</w:tblCellMar></w:tblPr>",
               f"<w:tblGrid>{grid}</w:tblGrid>"]
        last = len(rows) - 1
        for index, row in enumerate(rows):
            top = index == 0
            bottom = index == header_rows - 1 or index == last
            cells = []
            for value, width, align in zip(row, widths_in, aligns):
                borders = ""
                if top:
                    borders += ('<w:top w:val="single" w:sz="12" w:space="0" '
                                'w:color="000000"/>')
                if bottom:
                    borders += ('<w:bottom w:val="single" w:sz="'
                                + ("12" if index == last else "6")
                                + '" w:space="0" w:color="000000"/>')
                border_xml = f"<w:tcBorders>{borders}</w:tcBorders>" if borders else ""
                bold = index < header_rows
                text, extra = (value if isinstance(value, tuple)
                               else (value, {}))
                run_kw = dict(size=size, bold=bold)
                run_kw.update(extra)
                cells.append(
                    f'<w:tc><w:tcPr><w:tcW w:w="{int(width * TWIP)}" '
                    f'w:type="dxa"/>{border_xml}'
                    '<w:vAlign w:val="center"/></w:tcPr>'
                    f"<w:p>{self._ppr(align=align, before=22, after=22, keep_next=True)}"
                    f"{self._run(text, **run_kw)}</w:p></w:tc>")
            # cantSplit keeps a row whole; keepNext on every row (above) keeps
            # the table with its caption instead of breaking across a column.
            xml.append("<w:tr><w:trPr><w:cantSplit/></w:trPr>"
                       f"{''.join(cells)}</w:tr>")
        xml.append("</w:tbl>")
        self.parts.append("".join(xml))
        self.para("", after=0, before=0)

    def column_break(self):
        self.parts.append('<w:p><w:r><w:br w:type="column"/></w:r></w:p>')

    def section_break_two_columns(self, gutter_in=0.33, width_in=3.335):
        """Ends the one-column title block; everything after is two-column."""
        self.parts.append(
            "<w:p><w:pPr><w:sectPr>"
            '<w:type w:val="continuous"/>'
            '<w:pgSz w:w="12240" w:h="15840"/>'
            '<w:pgMar w:top="1080" w:right="1080" w:bottom="1440" '
            'w:left="1080" w:header="720" w:footer="720" w:gutter="0"/>'
            '<w:cols w:space="720"/>'
            "</w:sectPr></w:pPr></w:p>")

    # -- packaging ---------------------------------------------------------

    def _document_xml(self):
        final_sect = (
            "<w:sectPr>"
            # WITHOUT this, w:type defaults to nextPage and the two-column
            # body starts on page 2, leaving the title block alone on page 1.
            '<w:type w:val="continuous"/>'
            '<w:pgSz w:w="12240" w:h="15840"/>'
            '<w:pgMar w:top="1080" w:right="1080" w:bottom="1440" '
            'w:left="1080" w:header="720" w:footer="720" w:gutter="0"/>'
            f'<w:cols w:num="2" w:space="{int(0.33 * TWIP)}" w:equalWidth="1"/>'
            "</w:sectPr>")
        # A continuous section break after the last paragraph makes Word
        # balance the two columns of the section it closes, instead of filling
        # the left column and leaving the right one empty on the final page.
        balance = ("<w:p><w:pPr><w:sectPr>"
                   '<w:type w:val="continuous"/>'
                   '<w:pgSz w:w="12240" w:h="15840"/>'
                   '<w:pgMar w:top="1080" w:right="1080" w:bottom="1440" '
                   'w:left="1080" w:header="720" w:footer="720" w:gutter="0"/>'
                   f'<w:cols w:num="2" w:space="{int(0.33 * TWIP)}" '
                   'w:equalWidth="1"/>'
                   "</w:sectPr></w:pPr></w:p>")
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f"<w:document {NS}><w:body>"
                + "".join(self.parts) + balance + final_sect
                + "</w:body></w:document>")

    def _styles_xml(self):
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f"<w:styles {NS}><w:docDefaults><w:rPrDefault><w:rPr>"
                f'<w:rFonts w:ascii="{self.font}" w:hAnsi="{self.font}"/>'
                f'<w:sz w:val="{int(self.size * 2)}"/>'
                "</w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>"
                '<w:spacing w:after="0" w:line="216" w:lineRule="auto"/>'
                "</w:pPr></w:pPrDefault></w:docDefaults>"
                '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
                "<w:name w:val=\"Normal\"/></w:style></w:styles>")

    def _document_rels(self):
        rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/'
                'package/2006/relationships">'
                '<Relationship Id="rIdStyles" Type="http://schemas.'
                'openxmlformats.org/officeDocument/2006/relationships/styles" '
                'Target="styles.xml"/>'
                '<Relationship Id="rIdSettings" Type="http://schemas.'
                'openxmlformats.org/officeDocument/2006/relationships/settings"'
                ' Target="settings.xml"/>']
        for index, (name, _) in enumerate(self.images, 1):
            rels.append(
                f'<Relationship Id="rIdImg{index}" Type="http://schemas.'
                'openxmlformats.org/officeDocument/2006/relationships/image" '
                f'Target="media/{name}"/>')
        rels.append("</Relationships>")
        return "".join(rels)

    def _settings_xml(self):
        # Without a compatibilityMode of 15, Word opens the file in
        # "Compatibility Mode" and says so in the title bar, which looks like
        # the document is damaged when it is only unlabelled.
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f"<w:settings {NS}><w:compat>"
                '<w:compatSetting w:name="compatibilityMode" '
                'w:uri="http://schemas.microsoft.com/office/word" w:val="15"/>'
                "</w:compat></w:settings>")

    def save(self, path):
        path = Path(path)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", CONTENT_TYPES)
            zf.writestr("_rels/.rels", ROOT_RELS)
            zf.writestr("docProps/core.xml", _core_xml(self.title, self.author))
            zf.writestr("docProps/app.xml", APP_XML)
            zf.writestr("word/document.xml", self._document_xml())
            zf.writestr("word/styles.xml", self._styles_xml())
            zf.writestr("word/settings.xml", self._settings_xml())
            zf.writestr("word/_rels/document.xml.rels", self._document_rels())
            for name, data in self.images:
                zf.writestr(f"word/media/{name}", data)
        return path
