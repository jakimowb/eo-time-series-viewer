import re
from pathlib import Path

REPO = Path(__file__).parents[2]
DIR_RST = REPO / 'doc/source'

rx_yaml_block = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)


def update_md(source: Path, target: Path):
    source = Path(source)
    target = Path(target)
    print(f'Update {target}')
    assert source.is_file()
    assert source.name.endswith('.md')
    if target.is_dir():
        target = target / source.name

    yml_block = ''

    if target.exists():
        # extract header with rst specific content

        with open(target) as f:
            match = rx_yaml_block.match(f.read())
            if match:
                yml_block = match.group()

    with open(source) as f:
        data = f.read()
        data = yml_block + data

    with open(target, 'w', encoding='utf8') as f:
        f.write(data)


def update_all():
    to_update = [
        (REPO / 'ABOUT.md', DIR_RST / 'general'),
        (REPO / 'CHANGELOG.md', DIR_RST / 'general'),
        (REPO / 'CONTRIBUTORS.md', DIR_RST / 'general'),
    ]

    for (src, dst) in to_update:
        update_md(src, dst)


if __name__ == '__main__':
    update_all()
