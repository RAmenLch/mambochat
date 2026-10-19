# 并发文件操作样例

下面每个样例三部分：原文件、同时发出的调用、期望结果。

## 测试文件

`/workspace/race_demo/app.py`

```python
# demo/app.py
import os
import sys

APP_NAME = "demo"
VERSION = "1.0.0"


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    config = load_config("config.yaml")
    print(f"{APP_NAME} v{VERSION}")
    print(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

---

## EC-01 同一个文件，两处不同位置同时改

**原文件**：上面的 `app.py`

**同时发出的调用**

| 调用 | `path` | `old_str` | `new_str` |
|------|--------|-----------|-----------|
| A | `/workspace/race_demo/app.py` | `import os\nimport sys` | `import os\nimport json\nimport sys` |
| B | `/workspace/race_demo/app.py` | `if __name__ == "__main__":\n    sys.exit(main())` | `if __name__ == "__main__":\n    raise SystemExit(main())` |

**期望结果**

```python
# demo/app.py
import os
import json
import sys

APP_NAME = "demo"
VERSION = "1.0.0"


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    config = load_config("config.yaml")
    print(f"{APP_NAME} v{VERSION}")
    print(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

---

## EC-02 同一个文件，三处不同位置同时改

**原文件**：上面的 `app.py`

**同时发出的调用**

| 调用 | `old_str` | `new_str` |
|------|-----------|-----------|
| A | `import os\nimport sys` | `import os\nimport json\nimport sys` |
| B | `VERSION = "1.0.0"` | `VERSION = "1.1.0"` |
| C | `if __name__ == "__main__":\n    sys.exit(main())` | `if __name__ == "__main__":\n    raise SystemExit(main())` |

**期望结果**

```python
# demo/app.py
import os
import json
import sys

APP_NAME = "demo"
VERSION = "1.1.0"


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    config = load_config("config.yaml")
    print(f"{APP_NAME} v{VERSION}")
    print(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

---

## EC-03 同一个文件，同一处位置同时改

**原文件**：上面的 `app.py`

**同时发出的调用**

| 调用 | `old_str` | `new_str` |
|------|-----------|-----------|
| A | `VERSION = "1.0.0"` | `VERSION = "1.1.0"` |
| B | `VERSION = "1.0.0"` | `VERSION = "1.2.0"` |

**期望结果**（两种都算对：一条成功、一条报找不到原文）

A 先执行时：

```python
# demo/app.py
import os
import sys

APP_NAME = "demo"
VERSION = "1.1.0"


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    config = load_config("config.yaml")
    print(f"{APP_NAME} v{VERSION}")
    print(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

B 先执行时：

```python
# demo/app.py
import os
import sys

APP_NAME = "demo"
VERSION = "1.2.0"


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    config = load_config("config.yaml")
    print(f"{APP_NAME} v{VERSION}")
    print(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

---

## EC-04 一个 `edit`，一个 `write(overwrite=True)`

**原文件**：上面的 `app.py`

**同时发出的调用**

| 调用 | 工具 | 参数 |
|------|------|------|
| A | `edit` | `path=/workspace/race_demo/app.py`，`old_str='VERSION = "1.0.0"'`，`new_str='VERSION = "1.1.0"'` |
| B | `write` | `path=/workspace/race_demo/app.py`，`overwrite=True`，`content` 是下面这份内容 |

B 的 `content`：

```python
# demo/app.py
print("replaced by write")
```

**期望结果**（谁先执行都一样）

```python
# demo/app.py
print("replaced by write")
```

---

## EC-05 一个 `edit`，一个 `delete`

**原文件**：`/workspace/race_demo/to_delete.py`

```python
# demo/to_delete.py
VERSION = "1.0.0"
KEEP = True
```

**同时发出的调用**

| 调用 | 工具 | 参数 |
|------|------|------|
| A | `edit` | `path=/workspace/race_demo/to_delete.py`，`old_str='VERSION = "1.0.0"'`，`new_str='VERSION = "1.1.0"'` |
| B | `delete` | `path=/workspace/race_demo/to_delete.py` |

**期望结果**

```text
/workspace/race_demo/to_delete.py   文件不存在
```

---

## EC-06 三个不同文件同时改

**原文件**：`/workspace/race_demo/ec06_0.py`、`ec06_1.py`、`ec06_2.py`，三个文件内容一样

```python
a = 1
b = 2
c = 3
```

**同时发出的调用**：3 条 `edit`，各自只改自己的文件，`old_str='b = 2'`，`new_str='b = 20'`

**期望结果**（三个文件都是这个内容）

```python
a = 1
b = 20
c = 3
```

---

## EC-07 大文件，头尾同时改

**原文件**：`/workspace/race_demo/big.py`，5000 行

```python
line_0001 = 1
line_0002 = 2
line_0003 = 3
...
line_4999 = 4999
line_5000 = 5000
```

**同时发出的调用**

| 调用 | `old_str` | `new_str` |
|------|-----------|-----------|
| A | `line_0001 = 1` | `line_0001 = 100` |
| B | `line_5000 = 5000` | `line_5000 = 500000` |

**期望结果**（还是 5000 行）

```python
line_0001 = 100
line_0002 = 2
line_0003 = 3
...
line_4999 = 4999
line_5000 = 500000
```

---

## EC-08 一边读，一边改

**原文件**：上面的 `app.py`

**同时发出的调用**

| 调用 | 工具 | 参数 |
|------|------|------|
| A | `edit` | `path=/workspace/race_demo/app.py`，`old_str='VERSION = "1.0.0"'`，`new_str='VERSION = "1.1.0"'` |
| B | `read` | `path=/workspace/race_demo/app.py`，`limit=None` |

**期望结果**（读到下面两份中的任意一份，都是完整 22 行）

```python
# demo/app.py
import os
import sys

APP_NAME = "demo"
VERSION = "1.0.0"


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    config = load_config("config.yaml")
    print(f"{APP_NAME} v{VERSION}")
    print(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

或者

```python
# demo/app.py
import os
import sys

APP_NAME = "demo"
VERSION = "1.1.0"


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    config = load_config("config.yaml")
    print(f"{APP_NAME} v{VERSION}")
    print(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

