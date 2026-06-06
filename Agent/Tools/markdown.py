"""Minimal Markdown to HTML converter."""

import re


def md_to_html(md: str) -> str:
    md = md.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _inline(text: str) -> str:
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', r'<img src="\2" alt="\1" style="max-width:100%">', text)
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        return text

    lines = md.split("\n")
    html = []
    in_list = False
    list_type = None

    def close_list():
        nonlocal in_list, list_type
        if in_list:
            html.append(f"</{list_type}>")
            in_list = False
            list_type = None

    for line in lines:
        h = re.match(r'^(#{1,3})\s+(.+)$', line)
        if h:
            close_list()
            html.append(f"<h{len(h.group(1))}>{_inline(h.group(2))}</h{len(h.group(1))}>")
            continue

        ul = re.match(r'^-\s+(.+)$', line)
        if ul:
            if not in_list or list_type != "ul":
                close_list()
                html.append("<ul>")
                in_list = True
                list_type = "ul"
            html.append(f"<li>{_inline(ul.group(1))}</li>")
            continue

        ol = re.match(r'^\d+\.\s+(.+)$', line)
        if ol:
            if not in_list or list_type != "ol":
                close_list()
                html.append("<ol>")
                in_list = True
                list_type = "ol"
            html.append(f"<li>{_inline(ol.group(1))}</li>")
            continue

        if not line.strip():
            close_list()
            continue

        close_list()
        html.append(f"<p>{_inline(line)}</p>")

    close_list()
    return "\n".join(html)
