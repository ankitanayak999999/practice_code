import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


def remove_sql_comments(sql: str) -> str:
    """Remove -- and /* */ comments while preserving quoted text."""
    result = []
    i = 0
    quote = None

    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""

        if quote:
            result.append(ch)

            # SQL escaped quote: '' or ""
            if ch == quote:
                if nxt == quote:
                    result.append(nxt)
                    i += 2
                    continue
                quote = None

            i += 1
            continue

        if ch in ("'", '"'):
            quote = ch
            result.append(ch)
            i += 1
            continue

        if ch == "-" and nxt == "-":
            i += 2
            while i < len(sql) and sql[i] not in "\r\n":
                i += 1
            result.append("\n")
            continue

        if ch == "/" and nxt == "*":
            i += 2
            while i + 1 < len(sql) and not (sql[i] == "*" and sql[i + 1] == "/"):
                i += 1
            i += 2
            result.append(" ")
            continue

        result.append(ch)
        i += 1

    return "".join(result)


def find_top_level_keyword(sql: str, keyword: str, start: int = 0) -> int:
    """Find a keyword outside parentheses and quoted strings."""
    keyword_upper = keyword.upper()
    depth = 0
    quote = None
    i = start

    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""

        if quote:
            if ch == quote:
                if nxt == quote:
                    i += 2
                    continue
                quote = None
            i += 1
            continue

        if ch in ("'", '"'):
            quote = ch
            i += 1
            continue

        if ch == "(":
            depth += 1
            i += 1
            continue

        if ch == ")":
            depth = max(0, depth - 1)
            i += 1
            continue

        if depth == 0 and sql[i:i + len(keyword)].upper() == keyword_upper:
            before = sql[i - 1] if i > 0 else " "
            after_pos = i + len(keyword)
            after = sql[after_pos] if after_pos < len(sql) else " "

            if not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_"):
                return i

        i += 1

    return -1


def split_top_level_commas(select_list: str) -> list[str]:
    """Split a SELECT list only at commas outside parentheses and quotes."""
    items = []
    current = []
    depth = 0
    quote = None
    i = 0

    while i < len(select_list):
        ch = select_list[i]
        nxt = select_list[i + 1] if i + 1 < len(select_list) else ""

        if quote:
            current.append(ch)
            if ch == quote:
                if nxt == quote:
                    current.append(nxt)
                    i += 2
                    continue
                quote = None
            i += 1
            continue

        if ch in ("'", '"'):
            quote = ch
            current.append(ch)
            i += 1
            continue

        if ch == "(":
            depth += 1
            current.append(ch)
            i += 1
            continue

        if ch == ")":
            depth = max(0, depth - 1)
            current.append(ch)
            i += 1
            continue

        if ch == "," and depth == 0:
            item = "".join(current).strip()
            if item:
                items.append(item)
            current = []
            i += 1
            continue

        current.append(ch)
        i += 1

    final_item = "".join(current).strip()
    if final_item:
        items.append(final_item)

    return items


def normalize_expression(expression: str) -> str:
    """Collapse whitespace so each mapped expression fits on one row."""
    return re.sub(r"\s+", " ", expression).strip()


def extract_select_columns(sql: str) -> list[str]:
    cleaned = remove_sql_comments(sql).strip().rstrip(";")

    select_pos = find_top_level_keyword(cleaned, "SELECT")
    if select_pos == -1:
        raise ValueError("No top-level SELECT was found.")

    from_pos = find_top_level_keyword(cleaned, "FROM", select_pos + len("SELECT"))
    if from_pos == -1:
        raise ValueError("No top-level FROM was found after SELECT.")

    select_list = cleaned[select_pos + len("SELECT"):from_pos].strip()

    # Remove DISTINCT/ALL only when it begins the SELECT list.
    select_list = re.sub(r"^(DISTINCT|ALL)\b", "", select_list, count=1, flags=re.IGNORECASE).strip()

    columns = split_top_level_commas(select_list)
    if not columns:
        raise ValueError("No SELECT expressions were found.")

    return [normalize_expression(col) for col in columns]


class UnionMappingReviewer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("UNION Column Mapping Reviewer")
        self.geometry("1450x850")
        self.minsize(1000, 650)

        self.query1_columns = []
        self.query2_columns = []

        self._build_ui()

    def _build_ui(self):
        toolbar = ttk.Frame(self, padding=8)
        toolbar.pack(fill="x")

        ttk.Button(toolbar, text="Open Query 1", command=lambda: self.open_file(self.sql1)).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Open Query 2", command=lambda: self.open_file(self.sql2)).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Compare SELECT Columns", command=self.compare).pack(side="left", padx=12)
        ttk.Button(toolbar, text="Clear", command=self.clear_all).pack(side="left", padx=3)

        self.status_var = tk.StringVar(value="Paste one SELECT query into each pane, then click Compare SELECT Columns.")
        ttk.Label(toolbar, textvariable=self.status_var).pack(side="left", padx=15)

        input_pane = ttk.Panedwindow(self, orient="horizontal")
        input_pane.pack(fill="both", expand=False, padx=8, pady=(0, 8))

        left_frame = ttk.LabelFrame(input_pane, text="Query 1", padding=5)
        right_frame = ttk.LabelFrame(input_pane, text="Query 2", padding=5)
        input_pane.add(left_frame, weight=1)
        input_pane.add(right_frame, weight=1)

        self.sql1 = self.make_text_editor(left_frame)
        self.sql2 = self.make_text_editor(right_frame)

        result_frame = ttk.LabelFrame(self, text="Column Mapping by UNION Position", padding=6)
        result_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.tree = ttk.Treeview(
            result_frame,
            columns=("position", "query1", "query2"),
            show="headings",
            selectmode="browse"
        )
        self.tree.heading("position", text="#")
        self.tree.heading("query1", text="Query 1 expression")
        self.tree.heading("query2", text="Query 2 expression")

        self.tree.column("position", width=55, minwidth=45, anchor="center", stretch=False)
        self.tree.column("query1", width=650, minwidth=250, anchor="w")
        self.tree.column("query2", width=650, minwidth=250, anchor="w")

        y_scroll = ttk.Scrollbar(result_frame, orient="vertical", command=self.tree.yview)
        x_scroll = ttk.Scrollbar(result_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        result_frame.rowconfigure(0, weight=1)
        result_frame.columnconfigure(0, weight=1)

        self.tree.tag_configure("missing")

        self.tree.bind("<Double-1>", self.show_full_expression)

    @staticmethod
    def make_text_editor(parent):
        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True)

        text = tk.Text(
            container,
            wrap="none",
            height=14,
            undo=True,
            font=("Consolas", 10)
        )
        y_scroll = ttk.Scrollbar(container, orient="vertical", command=text.yview)
        x_scroll = ttk.Scrollbar(container, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        text.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        return text

    def open_file(self, target_text):
        path = filedialog.askopenfilename(
            title="Open SQL file",
            filetypes=[("SQL files", "*.sql"), ("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8-sig") as file:
                content = file.read()
        except UnicodeDecodeError:
            with open(path, "r", encoding="latin-1") as file:
                content = file.read()
        except OSError as exc:
            messagebox.showerror("Open file failed", str(exc))
            return

        target_text.delete("1.0", "end")
        target_text.insert("1.0", content)

    def compare(self):
        sql1 = self.sql1.get("1.0", "end").strip()
        sql2 = self.sql2.get("1.0", "end").strip()

        if not sql1 or not sql2:
            messagebox.showwarning("Missing SQL", "Paste or open both SQL queries first.")
            return

        try:
            self.query1_columns = extract_select_columns(sql1)
            self.query2_columns = extract_select_columns(sql2)
        except ValueError as exc:
            messagebox.showerror("Could not parse SQL", str(exc))
            return

        self.tree.delete(*self.tree.get_children())

        max_count = max(len(self.query1_columns), len(self.query2_columns))
        for index in range(max_count):
            left = self.query1_columns[index] if index < len(self.query1_columns) else "<MISSING>"
            right = self.query2_columns[index] if index < len(self.query2_columns) else "<MISSING>"
            tags = ("missing",) if left == "<MISSING>" or right == "<MISSING>" else ()
            self.tree.insert("", "end", values=(index + 1, left, right), tags=tags)

        count1 = len(self.query1_columns)
        count2 = len(self.query2_columns)

        if count1 == count2:
            self.status_var.set(f"Both queries contain {count1} output columns. Mapping is shown by position.")
        else:
            self.status_var.set(
                f"Column-count mismatch: Query 1 = {count1}, Query 2 = {count2}. "
                "Missing positions are marked as <MISSING>."
            )

    def show_full_expression(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return

        values = self.tree.item(selected[0], "values")
        position, left, right = values

        popup = tk.Toplevel(self)
        popup.title(f"Full Expressions — Position {position}")
        popup.geometry("1100x500")

        pane = ttk.Panedwindow(popup, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=8, pady=8)

        for title, value in (("Query 1", left), ("Query 2", right)):
            frame = ttk.LabelFrame(pane, text=title, padding=5)
            pane.add(frame, weight=1)

            text = tk.Text(frame, wrap="word", font=("Consolas", 11))
            text.pack(fill="both", expand=True)
            text.insert("1.0", value)
            text.configure(state="disabled")

    def clear_all(self):
        self.sql1.delete("1.0", "end")
        self.sql2.delete("1.0", "end")
        self.tree.delete(*self.tree.get_children())
        self.status_var.set("Paste one SELECT query into each pane, then click Compare SELECT Columns.")


if __name__ == "__main__":
    app = UnionMappingReviewer()
    app.mainloop()

