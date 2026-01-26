import re
import html as html_lib
from bs4 import BeautifulSoup

def strip_html_tags(text: str) -> str:
    """移除HTML标签，不使用get_text；a 标签转为 文本[链接]"""
    if not text:
        return ""
    # 用 BeautifulSoup 解析片段，避免残留属性碎片
    soup = BeautifulSoup(text, "html.parser")

    # a 标签转为 Markdown 链接: [文本](链接)
    for a in soup.find_all("a"):
        href = (a.get("href") or "").strip()
        inner_text = "".join(a.stripped_strings).strip()
        if inner_text and href:
            replacement = f"[{inner_text}]({href})"
        elif inner_text:
            replacement = inner_text
        elif href:
            replacement = f"({href})"
        else:
            replacement = ""
        a.replace_with(replacement)

    # 其他标签移除，仅保留文本
    cleaned = " ".join(soup.stripped_strings).strip()
    cleaned = re.sub(r"\s+([,.;:?!])", r"\1", cleaned)
    return html_lib.unescape(cleaned)


def extract_between(html: str, start: str, end: str) -> str:
    """截取start与end之间的内容（包含顺序）"""
    if not html:
        return ""
    start_idx = html.find(start)
    if start_idx == -1:
        return ""
    start_idx += len(start)
    end_idx = html.find(end, start_idx)
    if end_idx == -1:
        return ""
    return html[start_idx:end_idx]


def extract_paragraphs_by_style(html: str) -> list:
    """按正文段落样式批量截取内容"""
    pattern = (
        r"<div\s+style=['\"][^>]*?"
        r"font-family:PublicoText[^>]*?"
        r"font-size:20px[^>]*?"
        r"line-height:30px[^>]*?"
        r"['\"]>(.*?)</div>"
    )
    return re.findall(pattern, html, flags=re.DOTALL)


def extract(html: str) -> dict:
    soup = BeautifulSoup(html, 'html.parser')

    data = {
        "time": None,
        "content_html": None,
        "content_text": None,
    }

    # 示例：时间
    time_raw = extract_between(html, "<time", "</time>")
    if time_raw:
        # 对于 <time ...>xxx</time> 需要移除开始标签属性
        time_raw = re.sub(r"^.*?>", "", time_raw, count=1, flags=re.DOTALL)
        data["time"] = strip_html_tags(time_raw)

    # 正文：先用bs4缩小范围，再按段落样式截取
    main = soup.find('main')
    article = main.find('article')
    title = main.select('article > div')[1].text
    
    content_all = main.select('article')[0].select('article > div')[4]
    ch = next(content_all.children)
        
    content = ch.find('div', attrs={'style':'display:block;min-width:0px;'}).find_all('div', recursive=False)[2]
    
    
    def parser_div(tag):
        if hasattr(tag, 'text'):
            return [tag.text]
        else:
            return [str(tag)]
    def parser_a(tag):
        return [f'[{tag.text}]({tag["href"]})']
    def parser_default(tag):
        if hasattr(tag, 'text'):
            return [tag.text]
        else:
            return [str(tag)]
    def parser_blockquote(tag): 
        return ["```blockquote\n\n"]+parser_content(tag)+['```']

    parser_dict = {
        'div': parser_div,
        'a': parser_a,
        'blockquote': parser_blockquote,
        'default': parser_default,
    }

    def parser_content(content):
        content_list = []
        for tag in content.find_all(recursive=False):
            name = tag.name
            if name in parser_dict.keys():
                func = parser_dict[name]
            else:
                func = parser_dict['default']
            content_list.extend(func(tag))
            content_list.append('\n\n')
        return content_list
    content_list = parser_content(content)
    
    if content_list:
        data["content_text"] = "".join(content_list)
        data["content_html"] = data["content_text"]

    return data

if __name__ == "__main__":
    html = open("save/MkuJK.html", "r", encoding="utf-8").read()
    result = extract(html)
    print(result)
