# pmis-tutorial-student.py
# 个人信息管理系统：数据库与信息管理作业增强版
# 功能：ER 图、多表 SQLite 存储、SQL 关联查询、新增、更新、删除、CSV 导出

from contextlib import contextmanager
from pathlib import Path
import sqlite3

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="个人信息管理系统",
    page_icon="📘",
    layout="wide",
)


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "records.db"
LEGACY_CSV_PATH = DATA_DIR / "records.csv"
DATA_DIR.mkdir(parents=True, exist_ok=True)

PERSON_COLUMNS = [
    "id",
    "name",
    "phone",
    "email",
    "department",
    "notes",
    "created_at",
]

HONOR_COLUMNS = [
    "id",
    "person_id",
    "title",
    "level",
    "issuer",
    "award_date",
    "notes",
    "legacy_record_id",
    "created_at",
]

SCHEDULE_COLUMNS = [
    "id",
    "person_id",
    "event_title",
    "event_date",
    "location",
    "status",
    "notes",
    "created_at",
]

HONOR_LEVELS = ["校级", "院级", "市级", "国家级", "其他"]
SCHEDULE_STATUS = ["未开始", "进行中", "已完成", "已取消"]


@contextmanager
def get_conn():
    """Create a SQLite connection with foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_sql(sql: str, params: tuple = ()) -> None:
    with get_conn() as conn:
        conn.execute(sql, params)


def query_df(sql: str, params: tuple = ()) -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS persons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                department TEXT,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS honors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                level TEXT NOT NULL,
                issuer TEXT,
                award_date TEXT,
                notes TEXT,
                legacy_record_id INTEGER UNIQUE,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (person_id)
                    REFERENCES persons(id)
                    ON UPDATE CASCADE
                    ON DELETE CASCADE
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id INTEGER NOT NULL,
                event_title TEXT NOT NULL,
                event_date TEXT NOT NULL,
                location TEXT,
                status TEXT NOT NULL DEFAULT '未开始',
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (person_id)
                    REFERENCES persons(id)
                    ON UPDATE CASCADE
                    ON DELETE CASCADE
            );
            """
        )


def seed_default_person() -> int:
    people = query_df("SELECT id FROM persons ORDER BY id LIMIT 1;")
    if not people.empty:
        return int(people.iloc[0]["id"])

    execute_sql(
        """
        INSERT INTO persons(name, phone, email, department, notes)
        VALUES (?, ?, ?, ?, ?);
        """,
        ("默认用户", "", "", "个人信息管理", "系统自动创建，可在“个人信息”中修改。"),
    )
    people = query_df("SELECT id FROM persons ORDER BY id LIMIT 1;")
    return int(people.iloc[0]["id"])


def migrate_legacy_records() -> None:
    """Move old one-table records into the honors table without deleting the original data."""
    default_person_id = seed_default_person()
    with get_conn() as conn:
        table_exists = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='records';
            """
        ).fetchone()
        if table_exists:
            rows = conn.execute(
                """
                SELECT id, title, category, notes, created_at
                FROM records
                ORDER BY id;
                """
            ).fetchall()
            for row in rows:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO honors
                        (person_id, title, level, issuer, award_date, notes, legacy_record_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        default_person_id,
                        row["title"],
                        "其他",
                        row["category"],
                        "",
                        row["notes"],
                        row["id"],
                        row["created_at"],
                    ),
                )

    if LEGACY_CSV_PATH.exists():
        try:
            df = pd.read_csv(LEGACY_CSV_PATH)
        except Exception:
            return
        needed = {"id", "title", "category", "notes", "created_at"}
        if not df.empty and needed.issubset(df.columns):
            with get_conn() as conn:
                for row in df[list(needed)].to_dict(orient="records"):
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO honors
                            (person_id, title, level, issuer, award_date, notes, legacy_record_id, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            default_person_id,
                            row["title"],
                            "其他",
                            row["category"],
                            "",
                            row["notes"],
                            int(row["id"]),
                            row["created_at"],
                        ),
                    )


def bootstrap() -> None:
    init_db()
    seed_default_person()
    migrate_legacy_records()


@st.cache_data(ttl=2)
def load_people() -> pd.DataFrame:
    return query_df("SELECT * FROM persons ORDER BY id;")


@st.cache_data(ttl=2)
def load_honor_view(level_filter: str = "全部") -> pd.DataFrame:
    sql = """
        SELECT
            h.id,
            p.name AS 姓名,
            h.title AS 荣誉名称,
            h.level AS 级别,
            h.issuer AS 颁发单位,
            h.award_date AS 获奖日期,
            h.notes AS 备注,
            h.created_at AS 创建时间
        FROM honors h
        JOIN persons p ON h.person_id = p.id
    """
    params: tuple = ()
    if level_filter != "全部":
        sql += " WHERE h.level = ?"
        params = (level_filter,)
    sql += " ORDER BY h.id DESC;"
    return query_df(sql, params)


@st.cache_data(ttl=2)
def load_schedule_view(status_filter: str = "全部") -> pd.DataFrame:
    sql = """
        SELECT
            s.id,
            p.name AS 姓名,
            s.event_title AS 日程事项,
            s.event_date AS 日期,
            s.location AS 地点,
            s.status AS 状态,
            s.notes AS 备注,
            s.created_at AS 创建时间
        FROM schedules s
        JOIN persons p ON s.person_id = p.id
    """
    params: tuple = ()
    if status_filter != "全部":
        sql += " WHERE s.status = ?"
        params = (status_filter,)
    sql += " ORDER BY s.event_date ASC, s.id DESC;"
    return query_df(sql, params)


def clear_cache_and_rerun() -> None:
    st.cache_data.clear()
    st.rerun()


def person_options(people: pd.DataFrame) -> dict[str, int]:
    return {
        f"{row['name']}（ID {row['id']}）": int(row["id"])
        for _, row in people.iterrows()
    }


def show_er_diagram() -> None:
    st.subheader("ER 图")
    st.graphviz_chart(
        """
        digraph {
            graph [rankdir=LR, bgcolor="transparent"];
            node [shape=record, style="rounded,filled", fillcolor="#F8FAFC", color="#CBD5E1", fontname="Microsoft YaHei"];
            edge [color="#64748B", fontname="Microsoft YaHei"];

            persons [label="{个人基本信息 persons|id 主键|name 姓名|phone 电话|email 邮箱|department 所属分类|notes 备注}"];
            honors [label="{个人荣誉 honors|id 主键|person_id 外键|title 荣誉名称|level 级别|issuer 颁发单位|award_date 获奖日期}"];
            schedules [label="{个人日程 schedules|id 主键|person_id 外键|event_title 日程事项|event_date 日期|status 状态|location 地点}"];

            persons -> honors [label="1 对多"];
            persons -> schedules [label="1 对多"];
        }
        """,
        use_container_width=True,
    )
    st.caption("数据库包含 3 张表：一个人可以关联多条日程和多条荣誉记录，满足多表关联加分项。")


def overview_tab() -> None:
    people = load_people()
    honors = load_honor_view()
    schedules = load_schedule_view()

    total_people = len(people)
    total_honors = len(honors)
    total_schedules = len(schedules)
    unfinished = len(schedules[schedules["状态"].isin(["未开始", "进行中"])]) if not schedules.empty else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("个人信息", total_people)
    c2.metric("荣誉记录", total_honors)
    c3.metric("日程记录", total_schedules)
    c4.metric("待办日程", unfinished)

    show_er_diagram()

    st.subheader("SQL 关联查询结果")
    left, right = st.columns(2)
    with left:
        st.write("荣誉表 JOIN 个人信息表")
        st.dataframe(honors, use_container_width=True, hide_index=True)
    with right:
        st.write("日程表 JOIN 个人信息表")
        st.dataframe(schedules, use_container_width=True, hide_index=True)

    st.download_button(
        "下载荣誉关联查询 CSV",
        honors.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
        file_name="honors_join_query.csv",
        mime="text/csv",
        use_container_width=True,
    )
    st.download_button(
        "下载日程关联查询 CSV",
        schedules.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
        file_name="schedules_join_query.csv",
        mime="text/csv",
        use_container_width=True,
    )


def people_tab() -> None:
    st.subheader("个人基本信息")
    people = load_people()
    st.dataframe(people, use_container_width=True, hide_index=True)

    with st.expander("新增个人信息", expanded=True):
        with st.form("add_person_form", clear_on_submit=True):
            name = st.text_input("姓名 *", key="add_person_name")
            phone = st.text_input("电话", key="add_person_phone")
            email = st.text_input("邮箱", key="add_person_email")
            department = st.text_input("所属分类", placeholder="例如：学生、课程、社团、家庭", key="add_person_department")
            notes = st.text_area("备注", height=90, key="add_person_notes")
            submitted = st.form_submit_button("新增", type="primary", use_container_width=True)

        if submitted:
            if not name.strip():
                st.error("姓名不能为空。")
            else:
                execute_sql(
                    """
                    INSERT INTO persons(name, phone, email, department, notes)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (name.strip(), phone.strip(), email.strip(), department.strip(), notes.strip()),
                )
                st.success("个人信息已新增。")
                clear_cache_and_rerun()

    if people.empty:
        return

    with st.expander("更新或删除个人信息"):
        options = person_options(people)
        selected = st.selectbox("选择要操作的个人信息", list(options.keys()), key="edit_person_select")
        person_id = options[selected]
        current = people[people["id"] == person_id].iloc[0]

        with st.form("edit_person_form"):
            name = st.text_input("姓名 *", value=current["name"] or "", key="edit_person_name")
            phone = st.text_input("电话", value=current["phone"] or "", key="edit_person_phone")
            email = st.text_input("邮箱", value=current["email"] or "", key="edit_person_email")
            department = st.text_input("所属分类", value=current["department"] or "", key="edit_person_department")
            notes = st.text_area("备注", value=current["notes"] or "", height=90, key="edit_person_notes")
            update_submitted = st.form_submit_button("保存更新", use_container_width=True)

        if update_submitted:
            if not name.strip():
                st.error("姓名不能为空。")
            else:
                execute_sql(
                    """
                    UPDATE persons
                    SET name = ?, phone = ?, email = ?, department = ?, notes = ?
                    WHERE id = ?;
                    """,
                    (name.strip(), phone.strip(), email.strip(), department.strip(), notes.strip(), person_id),
                )
                st.success("个人信息已更新。")
                clear_cache_and_rerun()

        confirm = st.checkbox("确认删除该个人信息，并同时删除关联日程和荣誉。")
        if st.button("删除个人信息", disabled=not confirm, use_container_width=True):
            execute_sql("DELETE FROM persons WHERE id = ?;", (person_id,))
            st.success("个人信息及关联记录已删除。")
            clear_cache_and_rerun()


def honors_tab() -> None:
    st.subheader("个人荣誉信息")
    people = load_people()
    if people.empty:
        st.info("请先新增个人基本信息。")
        return

    level_filter = st.selectbox("按级别筛选", ["全部"] + HONOR_LEVELS)
    honors = load_honor_view(level_filter)
    st.dataframe(honors, use_container_width=True, hide_index=True)

    options = person_options(people)
    with st.expander("新增荣誉", expanded=True):
        with st.form("add_honor_form", clear_on_submit=True):
            person_label = st.selectbox("关联个人 *", list(options.keys()), key="add_honor_person")
            title = st.text_input("荣誉名称 *", key="add_honor_title")
            level = st.selectbox("级别 *", HONOR_LEVELS, key="add_honor_level")
            issuer = st.text_input("颁发单位", key="add_honor_issuer")
            award_date = st.date_input("获奖日期", key="add_honor_award_date")
            notes = st.text_area("备注", height=90, key="add_honor_notes")
            submitted = st.form_submit_button("新增荣誉", type="primary", use_container_width=True)

        if submitted:
            if not title.strip():
                st.error("荣誉名称不能为空。")
            else:
                execute_sql(
                    """
                    INSERT INTO honors(person_id, title, level, issuer, award_date, notes)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (
                        options[person_label],
                        title.strip(),
                        level,
                        issuer.strip(),
                        award_date.isoformat() if award_date else "",
                        notes.strip(),
                    ),
                )
                st.success("荣誉记录已新增。")
                clear_cache_and_rerun()

    raw_honors = query_df("SELECT * FROM honors ORDER BY id DESC;")
    if raw_honors.empty:
        return

    with st.expander("更新或删除荣誉"):
        honor_options = {
            f"{row['title']}（ID {row['id']}）": int(row["id"])
            for _, row in raw_honors.iterrows()
        }
        selected = st.selectbox("选择荣誉记录", list(honor_options.keys()))
        honor_id = honor_options[selected]
        current = raw_honors[raw_honors["id"] == honor_id].iloc[0]

        person_id_values = list(options.values())
        current_person_index = person_id_values.index(int(current["person_id"])) if int(current["person_id"]) in person_id_values else 0
        with st.form("edit_honor_form"):
            person_label = st.selectbox("关联个人 *", list(options.keys()), index=current_person_index, key="edit_honor_person")
            title = st.text_input("荣誉名称 *", value=current["title"] or "", key="edit_honor_title")
            level_index = HONOR_LEVELS.index(current["level"]) if current["level"] in HONOR_LEVELS else 0
            level = st.selectbox("级别 *", HONOR_LEVELS, index=level_index, key="edit_honor_level")
            issuer = st.text_input("颁发单位", value=current["issuer"] or "", key="edit_honor_issuer")
            award_date = st.text_input("获奖日期", value=current["award_date"] or "", placeholder="YYYY-MM-DD", key="edit_honor_award_date")
            notes = st.text_area("备注", value=current["notes"] or "", height=90, key="edit_honor_notes")
            update_submitted = st.form_submit_button("保存更新", use_container_width=True)

        if update_submitted:
            if not title.strip():
                st.error("荣誉名称不能为空。")
            else:
                execute_sql(
                    """
                    UPDATE honors
                    SET person_id = ?, title = ?, level = ?, issuer = ?, award_date = ?, notes = ?
                    WHERE id = ?;
                    """,
                    (
                        options[person_label],
                        title.strip(),
                        level,
                        issuer.strip(),
                        award_date.strip(),
                        notes.strip(),
                        honor_id,
                    ),
                )
                st.success("荣誉记录已更新。")
                clear_cache_and_rerun()

        if st.button("删除该荣誉记录", use_container_width=True):
            execute_sql("DELETE FROM honors WHERE id = ?;", (honor_id,))
            st.success("荣誉记录已删除。")
            clear_cache_and_rerun()


def schedules_tab() -> None:
    st.subheader("个人日程信息")
    people = load_people()
    if people.empty:
        st.info("请先新增个人基本信息。")
        return

    status_filter = st.selectbox("按状态筛选", ["全部"] + SCHEDULE_STATUS)
    schedules = load_schedule_view(status_filter)
    st.dataframe(schedules, use_container_width=True, hide_index=True)

    options = person_options(people)
    with st.expander("新增日程", expanded=True):
        with st.form("add_schedule_form", clear_on_submit=True):
            person_label = st.selectbox("关联个人 *", list(options.keys()), key="add_schedule_person")
            event_title = st.text_input("日程事项 *", key="add_schedule_title")
            event_date = st.date_input("日期", key="add_schedule_date")
            location = st.text_input("地点", key="add_schedule_location")
            status = st.selectbox("状态", SCHEDULE_STATUS, key="add_schedule_status")
            notes = st.text_area("备注", height=90, key="add_schedule_notes")
            submitted = st.form_submit_button("新增日程", type="primary", use_container_width=True)

        if submitted:
            if not event_title.strip():
                st.error("日程事项不能为空。")
            else:
                execute_sql(
                    """
                    INSERT INTO schedules(person_id, event_title, event_date, location, status, notes)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (
                        options[person_label],
                        event_title.strip(),
                        event_date.isoformat(),
                        location.strip(),
                        status,
                        notes.strip(),
                    ),
                )
                st.success("日程记录已新增。")
                clear_cache_and_rerun()

    raw_schedules = query_df("SELECT * FROM schedules ORDER BY event_date ASC, id DESC;")
    if raw_schedules.empty:
        return

    with st.expander("更新或删除日程"):
        schedule_options = {
            f"{row['event_title']}（ID {row['id']}）": int(row["id"])
            for _, row in raw_schedules.iterrows()
        }
        selected = st.selectbox("选择日程记录", list(schedule_options.keys()))
        schedule_id = schedule_options[selected]
        current = raw_schedules[raw_schedules["id"] == schedule_id].iloc[0]

        person_id_values = list(options.values())
        current_person_index = person_id_values.index(int(current["person_id"])) if int(current["person_id"]) in person_id_values else 0
        with st.form("edit_schedule_form"):
            person_label = st.selectbox("关联个人 *", list(options.keys()), index=current_person_index, key="edit_schedule_person")
            event_title = st.text_input("日程事项 *", value=current["event_title"] or "", key="edit_schedule_title")
            event_date = st.text_input("日期", value=current["event_date"] or "", placeholder="YYYY-MM-DD", key="edit_schedule_date")
            location = st.text_input("地点", value=current["location"] or "", key="edit_schedule_location")
            status_index = SCHEDULE_STATUS.index(current["status"]) if current["status"] in SCHEDULE_STATUS else 0
            status = st.selectbox("状态", SCHEDULE_STATUS, index=status_index, key="edit_schedule_status")
            notes = st.text_area("备注", value=current["notes"] or "", height=90, key="edit_schedule_notes")
            update_submitted = st.form_submit_button("保存更新", use_container_width=True)

        if update_submitted:
            if not event_title.strip():
                st.error("日程事项不能为空。")
            else:
                execute_sql(
                    """
                    UPDATE schedules
                    SET person_id = ?, event_title = ?, event_date = ?, location = ?, status = ?, notes = ?
                    WHERE id = ?;
                    """,
                    (
                        options[person_label],
                        event_title.strip(),
                        event_date.strip(),
                        location.strip(),
                        status,
                        notes.strip(),
                        schedule_id,
                    ),
                )
                st.success("日程记录已更新。")
                clear_cache_and_rerun()

        if st.button("删除该日程记录", use_container_width=True):
            execute_sql("DELETE FROM schedules WHERE id = ?;", (schedule_id,))
            st.success("日程记录已删除。")
            clear_cache_and_rerun()


def sql_tab() -> None:
    st.subheader("SQL 查询演示")
    st.caption("这里用于展示作业要求中的 Select、Join、Project。仅允许 SELECT 查询，避免误删或误改数据。")

    examples = {
        "查询所有个人信息": "SELECT id, name, phone, email, department FROM persons ORDER BY id;",
        "荣誉关联查询": """
SELECT p.name, h.title, h.level, h.issuer, h.award_date
FROM honors h
JOIN persons p ON h.person_id = p.id
ORDER BY h.id DESC;
""".strip(),
        "日程关联查询": """
SELECT p.name, s.event_title, s.event_date, s.location, s.status
FROM schedules s
JOIN persons p ON s.person_id = p.id
ORDER BY s.event_date ASC;
""".strip(),
    }
    selected = st.selectbox("选择示例 SQL", list(examples.keys()))
    sql = st.text_area("SQL 语句", value=examples[selected], height=180)

    if st.button("执行查询", type="primary", use_container_width=True):
        normalized = sql.strip().lower()
        if not normalized.startswith("select"):
            st.error("为了保护数据，这里只允许执行 SELECT 查询。")
            return
        try:
            result = query_df(sql)
            st.dataframe(result, use_container_width=True, hide_index=True)
        except Exception as exc:
            st.error(f"SQL 执行失败：{exc}")


def main() -> None:
    bootstrap()

    st.title("个人信息管理系统")
    st.caption(
        "基于 SQLite 的多表信息系统，覆盖数据读取与连接、新增、删除、更新，并展示 ER 图。"
    )

    tab_overview, tab_people, tab_honors, tab_schedules, tab_sql = st.tabs(
        ["总览与 ER 图", "个人信息", "个人荣誉", "个人日程", "SQL 查询"]
    )

    with tab_overview:
        overview_tab()
    with tab_people:
        people_tab()
    with tab_honors:
        honors_tab()
    with tab_schedules:
        schedules_tab()
    with tab_sql:
        sql_tab()


if __name__ == "__main__":
    main()
