import pathlib

test_dir = pathlib.Path(r'c:/Users/fandr/Desktop/microservice/ETHPrague2026/gigaservice/tests')
patterns = [
    ('"/auth/', '"/api/v1/auth/'),
    ('"/sensors/', '"/api/v1/sensors/'),
    ('"/packages/', '"/api/v1/packages/'),
    ('"/stats/', '"/api/v1/stats/'),
    ('"/trackers/', '"/api/v1/trackers/'),
]

for py in test_dir.rglob('*.py'):
    content = py.read_text(encoding='utf-8')
    original = content
    for old, new in patterns:
        content = content.replace(old, new)
    if content != original:
        py.write_text(content, encoding='utf-8')
        print(f'Updated: {py.name}')

print('Done')
