"""A very small Markdown-to-HTML converter for trial reports.

Supports headings, bullet lists, paragraphs, fenced code, **bold**, `code` and [links](https://...).
Everything is HTML-escaped first; only http(s) links become anchors."""
import html
import re

LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)\"'<>]+)\)")


def inline(s):
    s = html.escape(s, quote=True)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return LINK_RE.sub(r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>', s)


def to_html(md):
    out, para, in_list, in_code, code = [], [], False, False, []

    def end_para():
        nonlocal para
        if para:
            out.append("<p>" + "<br>".join(inline(x) for x in para) + "</p>")
            para = []

    def end_list():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for line in str(md or "").splitlines():
        if line.strip().startswith("```"):
            if in_code:
                out.append("<pre>" + html.escape("\n".join(code)) + "</pre>")
                in_code, code = False, []
            else:
                end_para()
                end_list()
                in_code = True
            continue
        if in_code:
            code.append(line)
            continue
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            end_para()
            end_list()
            lvl = min(4, len(m.group(1)) + 1)
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
        elif re.match(r"^\s*[-*]\s+", line):
            end_para()
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append("<li>" + inline(re.sub(r"^\s*[-*]\s+", "", line)) + "</li>")
        elif not line.strip():
            end_para()
            end_list()
        else:
            end_list()
            para.append(line)
    if in_code:
        out.append("<pre>" + html.escape("\n".join(code)) + "</pre>")
    end_para()
    end_list()
    return "\n".join(out)


def to_plain(md):
    """Markdown -> plain text for channels without Markdown: [t](u) -> t (u), drop **, `, <font> tags."""
    s = LINK_RE.sub(r"\1 (\2)", str(md or ""))
    s = re.sub(r"</?font[^>]*>", "", s)
    return s.replace("**", "").replace("`", "")
