# Docs site (MkDocs) — isolated from the batplot Python package

This folder powers the **GitHub Pages user manual**. It is **not** imported by
`batplot` at runtime and is **not** included in the PyPI wheel.

## Preview locally

```text
pip install mkdocs-material
mkdocs serve
```

## Re-import from Word

```text
pip install mammoth
python scripts/import_user_manual_docx.py "/path/to/batplot_user_manual.docx"
```

## Add pictures

1. Save files under `docs/images/` (e.g. `docs/images/my_plot.png`).
2. In a chapter Markdown file:

```markdown
![Short description](images/my_plot.png)
```

## Fonts / italics

- **Code blocks**: commands must use Markdown fences:

  ````markdown
  ```text
  batplot file.xy --xaxis 2theta --i
  ```
  ````

  Styling is in `docs/stylesheets/extra.css` (dark block + JetBrains Mono).

- **Italic *batplot***: write `*batplot*` in Markdown.
  Plain `batplot` without asterisks stays upright.
