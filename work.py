import streamlit as st
import pandas as pd
import datetime
import plotly.graph_objects as go
from io import BytesIO

st.set_page_config(page_title="Construction Planner", layout="wide")
st.title("Construction Schedule Planner")

st.sidebar.header("Add New Task")

# Initialize session state
if "tasks" not in st.session_state:
    st.session_state.tasks = []

# Sidebar form to add new task
with st.sidebar.form("task_form"):
    task_name = st.text_input("Task Name").strip()
    duration = st.number_input("Duration (days)", min_value=1, value=1)
    start_date = st.date_input("Start Date", datetime.date.today())
    dependency = st.text_input("Depends on (task name, optional)").strip()
    progress = st.slider("Progress (%)", 0, 100, 0)
    submitted = st.form_submit_button("Add Task")

# Add task with validation
if submitted:
    existing_names = [task["Task"].lower() for task in st.session_state.tasks]
    if not task_name:
        st.sidebar.warning("❌ Task name cannot be empty.")
    elif task_name.lower() in existing_names:
        st.sidebar.warning("⚠️ Task name already exists.")
    else:
        st.session_state.tasks.append({
            "Task": task_name,
            "Duration": duration,
            "Start Date": start_date,
            "Depends On": dependency,
            "Progress": progress,
            "Actual Start": None,
            "Actual Finish": None,
            "Delay": None
        })
        st.sidebar.success("✅ Task added!")

# Load tasks from uploaded Excel file
@st.cache_data(show_spinner=False)
def load_tasks_from_excel(uploaded_file):
    df = pd.read_excel(uploaded_file, engine='openpyxl')
    if "Task" in df.columns and "Duration" in df.columns:
        df["Actual Start"] = pd.to_datetime(df.get("Actual Start"))
        df["Actual Finish"] = pd.to_datetime(df.get("Actual Finish"))
        df["Depends On"] = df.get("Depends On", "")
        df["Progress"] = df.get("Progress", 0)
        df["Start Date"] = pd.to_datetime(df["Start Date"])

        delays = []
        for _, row in df.iterrows():
            if pd.notnull(row["Actual Finish"]):
                planned_finish = row["Start Date"] + pd.Timedelta(days=row["Duration"] - 1)
                delay_days = (row["Actual Finish"] - planned_finish).days
                delays.append(delay_days if delay_days != 0 else 0)
            else:
                delays.append(None)
        df["Delay"] = delays

        return df.to_dict(orient="records")
    else:
        raise ValueError("Invalid Excel file format")

uploaded_file = st.sidebar.file_uploader("Upload Excel File", type=["xlsx"])
if uploaded_file is not None:
    try:
        st.session_state.tasks = load_tasks_from_excel(uploaded_file)
        st.sidebar.success("📂 Data loaded successfully!")
    except Exception as e:
        st.sidebar.error(f"❌ Error loading file: {e}")

def save_tasks_to_excel():
    if st.session_state.tasks:
        df = pd.DataFrame(st.session_state.tasks)
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Tasks")
        output.seek(0)
        return output
    else:
        st.sidebar.warning("No tasks to save!")

if st.sidebar.button("Save Tasks to Excel"):
    output = save_tasks_to_excel()
    if output:
        st.sidebar.download_button(
            label="Download Tasks as Excel",
            data=output,
            file_name="tasks_schedule.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

if st.session_state.tasks:
    df = pd.DataFrame(st.session_state.tasks)
    df["Start Date"] = pd.to_datetime(df["Start Date"]).dt.strftime("%Y-%m-%d")
    df["Actual Start"] = pd.to_datetime(df["Actual Start"]).dt.strftime("%Y-%m-%d")
    df["Actual Finish"] = pd.to_datetime(df["Actual Finish"]).dt.strftime("%Y-%m-%d")
    df["End Date"] = (pd.to_datetime(df["Start Date"]) + pd.to_timedelta(df["Duration"] - 1, unit='D')).dt.strftime("%Y-%m-%d")
    df["Depends On"] = df["Depends On"].fillna("").astype(str).str.strip()

    tab1, tab2 = st.tabs(["📜 Project Schedule", "📈 Gantt Chart"])

    with tab1:
        st.subheader("📜 Project Schedule")
        st.dataframe(df)

        st.subheader("✅ Task Progress")
        st.subheader("✏️ Edit Task")
        task_names = [t["Task"] for t in st.session_state.tasks]
        selected_task = st.selectbox("Select a task", task_names)

        selected_data = next((t for t in st.session_state.tasks if t["Task"] == selected_task), {})
        default_progress = selected_data.get("Progress", 0)

        actual_start_val = selected_data.get("Actual Start")
        actual_finish_val = selected_data.get("Actual Finish")
        default_start = pd.to_datetime(actual_start_val).date() if pd.notnull(actual_start_val) else datetime.date.today()
        default_finish = pd.to_datetime(actual_finish_val).date() if pd.notnull(actual_finish_val) else datetime.date.today()

        col1, col2, col3 = st.columns(3)
        with col1:
            new_progress = st.slider("Update progress (%)", 0, 100, value=default_progress, key="progress_slider")
        with col2:
            actual_start = st.date_input("Actual Start Date", value=default_start, key="actual_start")
        with col3:
            actual_finish = st.date_input("Actual Finish Date", value=default_finish, key="actual_finish")

        if st.button("Update Task"):
            for task in st.session_state.tasks:
                if task["Task"] == selected_task:
                    task["Progress"] = new_progress
                    task["Actual Start"] = actual_start.strftime("%Y-%m-%d") if actual_start else None
                    task["Actual Finish"] = actual_finish.strftime("%Y-%m-%d") if actual_finish else None
                    if actual_finish:
                        planned_finish = pd.to_datetime(task["Start Date"]) + pd.to_timedelta(task["Duration"] - 1, unit='D')
                        delay_days = (pd.to_datetime(actual_finish) - planned_finish).days
                        task["Delay"] = delay_days if delay_days != 0 else 0
                    else:
                        task["Delay"] = None
            st.success("Task updated!")
            st.rerun()

    with tab2:
        st.subheader("📈 Gantt Chart with Progress and Dependencies")
        gantt_df = df.copy()
        gantt_df["Task Label"] = gantt_df["Task"] + " #" + gantt_df.index.astype(str)

        fig = go.Figure()
        day_to_ms = 86400000

        try:
            added_legends = set()
            for i, row in gantt_df.iterrows():
                start_ts = pd.to_datetime(row["Start Date"]).timestamp() * 1000
                duration_ms = row["Duration"] * day_to_ms
                offset = 0

                # Planned + Progress (upper half)
                fig.add_trace(go.Bar(
                    x=[duration_ms], y=[row["Task Label"]], orientation="h",
                    base=start_ts, marker=dict(color="lightgray"),
                    width=0.4, offset=-0.2,
                    name="Planned", showlegend="Planned" not in added_legends,
                    hovertemplate=f"<b>{row['Task']}</b><br>Start: {row['Start Date']}<br>End: {row['End Date']}<extra></extra>"
                ))
                added_legends.add("Planned")

                if row["Progress"] > 0:
                    progress_duration_ms = row["Duration"] * (row["Progress"] / 100) * day_to_ms
                    fig.add_trace(go.Bar(
                        x=[progress_duration_ms], y=[row["Task Label"]], orientation="h",
                        base=start_ts, marker=dict(color="green", opacity=1),
                        width=0.4, offset=-0.2,
                        name="Progress", showlegend="Progress" not in added_legends,
                        hovertemplate=f"<b>{row['Task']} Progress</b><br>{row['Progress']}% Complete<extra></extra>"
                    ))
                    added_legends.add("Progress")

                # Actual (lower half)
                if pd.notnull(row["Actual Start"]) and pd.notnull(row["Actual Finish"]):
                    actual_start_ts = pd.to_datetime(row["Actual Start"]).timestamp() * 1000
                    actual_duration_ms = (pd.to_datetime(row["Actual Finish"]) - pd.to_datetime(row["Actual Start"]) + pd.Timedelta(days=1)).total_seconds() * 1000

                    delay_color = "#ffa500"
                    name = "Actual (On Time)"
                    if isinstance(row["Delay"], (int, float)):
                        if row["Delay"] > 0:
                            delay_color = "#ff4c4c"; name = "Actual (Delayed)"
                        elif row["Delay"] < 0:
                            delay_color = "#ffd700"; name = "Actual (Ahead)"

                    fig.add_trace(go.Bar(
                        x=[actual_duration_ms], y=[row["Task Label"]], orientation="h",
                        base=actual_start_ts, marker=dict(color=delay_color, opacity=0.5),
                        width=0.4, offset=0.2,
                        name=name, showlegend=name not in added_legends,
                        hovertemplate=f"<b>{row['Task']} Actual</b><br>Start: {row['Actual Start']}<br>Finish: {row['Actual Finish']}<br>Delay: {row['Delay']} day(s)<extra></extra>"
                    ))
                    added_legends.add(name)

                # Dependency arrow (perpendicular shape)
                if row["Depends On"]:
                    dep_task = gantt_df[gantt_df["Task"].str.lower() == row["Depends On"].lower()]
                    if not dep_task.empty:
                        dep_row = dep_task.iloc[0]
                        dep_end_ts = pd.to_datetime(dep_row["End Date"]).timestamp() * 1000 + day_to_ms

                        # Draw vertical line from predecessor to same y-level as current
                        fig.add_shape(type="line",
                                      x0=dep_end_ts, y0=dep_row["Task Label"],
                                      x1=dep_end_ts, y1=row["Task Label"],
                                      line=dict(color="rgba(255,0,0,1)", width=1))

                        # Draw horizontal line to current task
                        fig.add_shape(type="line",
                                      x0=dep_end_ts, y0=row["Task Label"],
                                      x1=start_ts - 100000, y1=row["Task Label"],
                                      line=dict(color="rgba(255,0,0,1)", width=1))

                        # Final arrow from near current to task start (fix with no text and allowarrowhead)
                        fig.add_annotation(
                            x=start_ts, y=row["Task Label"],
                            ax=dep_end_ts, ay=row["Task Label"],
                            xref="x", yref="y", axref="x", ayref="y",
                            text="",
                            showarrow=True,
                            arrowhead=2,
                            arrowsize=1,
                            arrowwidth=1,
                            arrowcolor="rgba(255,0,0,1)"
                        )

            fig.update_yaxes(autorange="reversed", title="Tasks", showgrid=True, tickfont=dict(size=14))
            fig.update_xaxes(type="date", title="Date", showgrid=True, tickformat="%Y-%m-%d", tickfont=dict(size=14))
            fig.update_layout(
                title={
                    'text': "Gantt Chart with Progress and Dependencies",
                    'x': 0.5, 'xanchor': 'center'
                },
                height=40 * len(gantt_df) + 200,
                barmode="overlay",
                plot_bgcolor='white',
                xaxis=dict(gridcolor='lightgray'),
                yaxis=dict(gridcolor='lightgray'),
                legend=dict(
                    yanchor="top",
                    y=1.0,
                    xanchor="right",
                    x=1.0,
                    bgcolor='rgba(255,255,255,0.7)',
                    bordercolor='gray',
                    borderwidth=1
                )
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(f"Error rendering chart: {e}")
else:
    st.info("🗒️ Add some tasks to get started!")

st.caption("Built with ❤️ using Streamlit and Plotly")


