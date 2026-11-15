import io, glob, os, re

os.chdir(r"C:\Users\Administrator\Desktop\obisidian\obisidian")
files = [f for f in glob.glob('*.md') + glob.glob('身份与记忆/*.md')
         if os.path.basename(f) != '最近变更.md']

print(f'{"笔记":<38} {"行数":>5} {"可执行":>6} {"代码块":>6}  操作层')
print('-' * 76)
rows = []
for f in sorted(files):
    s = io.open(f, encoding='utf-8', errors='ignore').read()
    lines = s.count('\n')
    cmdblock = len(re.findall(r'```(?:bash|powershell|sh|shell|cmd)\n', s))
    inline = len(re.findall(r'`(?:bash |C:/[^`]+|python |node |curl |git |adb |pip )', s))
    has_code = len(re.findall(r'```\n', s))
    # 「怎么用」标志：有明确的步骤/命令/接口/字段
    steps = len(re.findall(r'^\s*(?:\d+\.|[-*])\s', s, re.M))
    howto = len(re.findall(r'(怎么用|如何|用法|步骤|第一步|执行|调用|接口|字段|参数|POST |GET )', s))
    score = cmdblock + inline
    verdict = '✓ 强' if score >= 4 else ('△ 中' if score >= 1 else '✗ 弱')
    rows.append((f, lines, score, has_code, howto, verdict))
    print(f'{f:<38} {lines:>5} {score:>6} {has_code:>6}  {verdict}')

print()
good = sum(1 for r in rows if r[5].startswith('✓'))
mid = sum(1 for r in rows if r[5].startswith('△'))
weak = sum(1 for r in rows if r[5].startswith('✗'))
print(f'可执行命令密度: ✓强 {good} / △中 {mid} / ✗弱 {weak}  (共 {len(rows)} 篇)')
print()
print('=== 缺操作层的笔记（按严重度排）===')
for f, lines, score, code, howto, v in sorted(rows, key=lambda x: x[2])[:8]:
    print(f'  {v}  {f:<38} 可执行={score}  "怎么用"类关键词={howto}')
