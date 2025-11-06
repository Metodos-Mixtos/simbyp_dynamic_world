#!/usr/bin/env python3
import json, re
from pathlib import Path

SECTION_PAT = re.compile(r"{{#(\w+)}}(.*?){{/\1}}", re.DOTALL)
TOKEN_PAT   = re.compile(r"{{\s*([\w\.]+)\s*}}")

def build_very_high_sections(sections):
    blocks = []
    for i, sec in enumerate(sections or [], start=1):
        bullets = "".join(f"<li>{b}</li>" for b in sec.get("bullets", []))
        block = f"""
        <div class="card">
          <h4 class="badge">Sección {i}</h4>
          <h3>{sec.get("title","Sección")}</h3>
          <ul>{bullets}</ul>
          <figure>
            <img src="{sec.get("image","#")}" alt="{sec.get("title","Sección")}" style="width:100%; border-radius:4px; border:1px solid #ccc;">
            <figcaption>Figura {i+1}. Imagen de Sentinel-2 para la sección {i}.</figcaption>
          </figure>
        </div>
        """
        blocks.append(block)
    return "\n".join(blocks)

def build_header(header_dict):
    if not isinstance(header_dict, dict):
        return ""
    logo = header_dict.get("LOGO", "#")
    alt = header_dict.get("ALT", "Header logo")
    height = header_dict.get("HEIGHT", "60px")
    return f"""
    <header>
      <img src="{logo}" alt="{alt}" style="height:{height};">
    </header>
    """

def render(template_path: Path, data_path: Path, out_path: Path):
    template = template_path.read_text(encoding="utf-8")
    data = json.loads(data_path.read_text(encoding="utf-8"))

    # Convierte el dict HEADER a HTML antes de renderizar
    data["HEADER"] = build_header(data.get("HEADER"))

    # Renderiza tokens + secciones
    html = render_template(template, data)

    out_path.write_text(html, encoding="utf-8")
    return out_path

def render_template(tpl: str, root: dict) -> str:
    def _render_block(block: str, ctx: dict) -> str:
        def _section(m):
            key, inner = m.group(1), m.group(2)
            arr = ctx.get(key, [])
            if not isinstance(arr, list):
                return ""
            out = []
            for item in arr:
                local = {**ctx, **(item if isinstance(item, dict) else {".": item})}
                out.append(_render_block(inner, local))
            return "".join(out)

        out = SECTION_PAT.sub(_section, block)

        def _token(m):
            k = m.group(1)
            return str(ctx.get(k, root.get(k, "")))
        return TOKEN_PAT.sub(_token, out)

    return _render_block(tpl, root)
