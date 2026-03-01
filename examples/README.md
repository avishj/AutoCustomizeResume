# Examples

Sample files to get you started. Copy them to the project root and fill in your details.

## Simple vs Advanced Resume

- `resume.simple.example.tex` is a minimal tagged resume, good for learning the tag syntax
- `resume.advanced.example.tex` is a full-featured resume with multiple sections, research, publications, and nested items

Both compile to PDF. Check the `.pdf` files to see what they look like.

## Setup

```bash
# 1. Copy config and env to project root
cp examples/config.example.yaml config.yaml
cp examples/.env.example .env

# 2. Fill in your details in config.yaml and add your API key to .env

# 3. Copy whichever sample resume you prefer (or use your own)
cp examples/resume.simple.example.tex resume.tex
# OR
cp examples/resume.advanced.example.tex resume.tex

# 4. Edit the template with your content, or add tags to your existing resume
#    See docs/TAGS.md for the tagging format
```

## Bring Your Own Template

You don't need to use these samples. Any LaTeX resume works. Just add the `%%% BEGIN` / `%%% END` tags around sections, items, and bullets you want the LLM to control. See [docs/TAGS.md](../docs/TAGS.md) for the full tagging specification. If your resume uses very different kind of LaTeX elements, some parts of the parser might fail, so prefer a template.
