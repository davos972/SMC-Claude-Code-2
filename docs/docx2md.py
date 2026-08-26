"""Convertit un .docx en Markdown avec la bibliotheque standard (ni pandoc ni python-docx).

Lit les membres du ZIP en memoire — rien n'est extrait sur le disque.
Gere : titres (Heading N / Titre N), listes a puces et numerotees, gras/italique, tableaux.
"""
import sys
import zipfile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _text_of_run(run):
    out = []
    for node in run:
        tag = node.tag
        if tag == W + "t":
            out.append(node.text or "")
        elif tag == W + "tab":
            out.append("\t")
        elif tag in (W + "br", W + "cr"):
            out.append("\n")
    return "".join(out)


def _run_is(run, prop):
    rpr = run.find(W + "rPr")
    if rpr is None:
        return False
    node = rpr.find(W + prop)
    if node is None:
        return False
    val = node.get(W + "val")
    return val not in ("0", "false", "none")


def _para_text(para):
    """Texte du paragraphe, avec gras/italique reportes en Markdown."""
    pieces = []
    for run in para.iter(W + "r"):
        txt = _text_of_run(run)
        if not txt:
            continue
        bold = _run_is(run, "b")
        italic = _run_is(run, "i")
        stripped = txt.strip()
        if stripped and (bold or italic):
            lead = txt[: len(txt) - len(txt.lstrip())]
            trail = txt[len(txt.rstrip()):]
            mark = "**" if bold else ""
            mark += "*" if italic else ""
            txt = f"{lead}{mark}{stripped}{mark}{trail}"
        pieces.append(txt)
    return "".join(pieces).strip()


def _style_of(para):
    ppr = para.find(W + "pPr")
    if ppr is None:
        return "", None
    style_node = ppr.find(W + "pStyle")
    style = style_node.get(W + "val", "") if style_node is not None else ""
    numpr = ppr.find(W + "numPr")
    return style, numpr


def _heading_level(style):
    s = style.lower()
    for prefix in ("heading", "titre"):
        if s.startswith(prefix):
            tail = s[len(prefix):].strip()
            if tail.isdigit():
                return int(tail)
    if s in ("title", "titre"):
        return 1
    return 0


def _cell_text(cell):
    parts = [_para_text(p) for p in cell.findall(W + "p")]
    return " ".join(x for x in parts if x).replace("|", "\\|")


def _table_md(tbl):
    rows = []
    for tr in tbl.findall(W + "tr"):
        rows.append([_cell_text(tc) for tc in tr.findall(W + "tc")])
    if not rows:
        return []
    width = max(len(r) for r in rows)
    if width == 1:
        # Encadre Word (tableau a une seule colonne) -> citation Markdown,
        # bien plus lisible qu'un tableau d'une cellule.
        out = []
        for r in rows:
            body = r[0].replace(chr(92) + "|", "|").strip()
            if body:
                out.append("> " + body)
                out.append("")
        return out
    rows = [r + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |",
           "|" + "---|" * width]
    for r in rows[1:]:
        out.append("| " + " | ".join(r) + " |")
    out.append("")
    return out


def convert(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml")
    root = ET.fromstring(xml)
    body = root.find(W + "body")
    lines = []
    for child in body:
        if child.tag == W + "p":
            style, numpr = _style_of(child)
            text = _para_text(child)
            if not text:
                continue
            lvl = _heading_level(style)
            if lvl:
                lines.append("")
                lines.append("#" * min(lvl, 6) + " " + text)
                lines.append("")
            elif numpr is not None:
                ilvl_node = numpr.find(W + "ilvl")
                depth = int(ilvl_node.get(W + "val", "0")) if ilvl_node is not None else 0
                lines.append("  " * depth + "- " + text)
            else:
                lines.append(text)
                lines.append("")
        elif child.tag == W + "tbl":
            lines.append("")
            lines.extend(_table_md(child))
    # compacte les lignes vides consecutives
    out, blank = [], False
    for ln in lines:
        if ln.strip() == "":
            if blank:
                continue
            blank = True
        else:
            blank = False
        out.append(ln.rstrip())
    return "\n".join(out).strip() + "\n"


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    md = convert(src)
    with open(dst, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(md)
    print(f"{src} -> {dst} ({md.count(chr(10)) + 1} lignes)")
