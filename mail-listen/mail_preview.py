"""Render stored mail markup in a restricted, offline preview document."""

from html import escape
from html.parser import HTMLParser
import re


class _MailPreviewParser(HTMLParser):
    tags = set('div p span font b strong i em u s strike br hr pre blockquote a ol ul li '
               'table caption colgroup col thead tbody tfoot tr th td h1 h2 h3 h4 h5 h6 '
               'img style center small sub sup address dl dt dd'.split())
    omitted = set('script iframe frame object embed svg math form title'.split())
    void = set('area base br col embed hr img input link meta param source track wbr'.split())
    attributes = set('style class title width height border cellpadding cellspacing align valign '
                     'colspan rowspan bgcolor color face size dir lang'.split())

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.omitting = []
        self.in_style = False

    def handle_starttag(self, tag, attrs):
        if self.omitting or tag in self.omitted:
            if tag not in self.void:
                self.omitting.append(tag)
            return
        if tag not in self.tags:
            return
        attributes = [(key, value) for key, value in attrs if key in self.attributes and value is not None]
        if tag == 'img':
            src = dict(attrs).get('src') or ''
            if not re.match(r'^data:image/(?:png|jpeg|gif|webp);base64,', src, re.I):
                return
            attributes.append(('src', src))
        self.parts.append('<' + tag + ''.join(f' {key}="{escape(value, quote=True)}"' for key, value in attributes) + '>')
        if tag == 'style':
            self.in_style = True

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.void:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.omitting:
            if tag in self.omitting:
                del self.omitting[len(self.omitting) - 1 - self.omitting[::-1].index(tag):]
            return
        if tag in self.tags and tag not in self.void:
            self.parts.append(f'</{tag}>')
        if tag == 'style':
            self.in_style = False

    def handle_data(self, data):
        if not self.omitting:
            self.parts.append(data if self.in_style else escape(data, quote=False))


def build_mail_preview(html_content):
    if not html_content:
        return None
    parser = _MailPreviewParser()
    parser.feed(html_content)
    parser.close()
    return ("<!doctype html><html><head><meta charset=\"utf-8\">"
            "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; "
            "style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'\">"
            "<meta name=\"referrer\" content=\"no-referrer\">"
            "<style>body{margin:16px;font:14px/1.6 sans-serif;overflow-wrap:break-word}"
            "table{border-collapse:collapse}img{max-width:100%}</style></head><body>"
            + ''.join(parser.parts) + '</body></html>')
