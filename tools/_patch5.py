import pathlib
src = pathlib.Path(r"D:\个人资料\项目\token看板\tokenboard\ui\win32.py").read_text(encoding="utf-8")
for pat in ["WM_RBUTTONUP", "WM_LBUTTONDOWN", "WM_LBUTTONUP", "WM_KEYDOWN", "def on_click", "def on_key"]:
    j = 0
    while True:
        k = src.find(pat, j)
        if k < 0:
            break
        print(pat, "->", k)
        j = k + 1
