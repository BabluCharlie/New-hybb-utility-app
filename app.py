import streamlit as st
from google.oauth2 import service_account
import gspread
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import pandas as pd

# CONFIG
SHEET_NAME = "Hybb Utility System"
WORKSHEET_NAME = "Requests"
SHARED_DRIVE_ID = "0AO88IQGAqsTKUk9PVA"

def get_credentials():
    return service_account.Credentials.from_service_account_file(
        'hybb-creds.json',
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )

def connect_to_sheet():
    creds = get_credentials()
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
    return sheet, creds

def save_image_to_drive(image_data, creds):
    service = build('drive', 'v3', credentials=creds)
    file_metadata = {
        'name': f"image_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg",
        'parents': [SHARED_DRIVE_ID],
    }
    media = MediaIoBaseUpload(io.BytesIO(image_data), mimetype='image/jpeg')
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id',
        supportsAllDrives=True
    ).execute()
    file_id = file.get("id")
    return f"https://drive.google.com/uc?export=view&id={file_id}"

def is_admin():
    st.sidebar.markdown("### 🔐 Admin Access")
    password = st.sidebar.text_input("Enter Admin Password", type="password")
    admin_name = st.sidebar.text_input("Your Name/Email (for action log)")
    return password == st.secrets.get("admin_password", "admin123"), admin_name

def main():
    st.markdown("""
        <style>.stApp { background-color: #e0f7e9; }</style>
    """, unsafe_allow_html=True)

    st.title("📋 HYBB Utility App")

    try:
        sheet, creds = connect_to_sheet()
    except Exception:
        st.error("⚠️ Cannot access Google Sheet. Please check sharing and API permissions.")
        st.stop()

    menu = st.sidebar.radio("📌 Menu", ["Submit Request", "Dashboard", "Admin Dashboard"])

    if menu == "Submit Request":
        st.subheader("📸 Submit Request")
        kitchen = st.selectbox("Select Kitchen", ["--Select--", "WFD01", "BSN01", "HSR01", "MAR01", "SKM01"])
        emp_name = st.text_input("Employee Name")
        emp_id = st.text_input("Employee ID")
        picture = st.camera_input("Take Photo (camera only)")

        if st.button("Submit Request"):
            if not all([kitchen != "--Select--", emp_name, emp_id, picture]):
                st.warning("⚠️ Please fill all fields and take a photo.")
            else:
                img_url = save_image_to_drive(picture.getvalue(), creds)
                sheet.append_row([
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    kitchen, emp_name, emp_id, img_url,
                    "Pending", "", ""
                ])
                st.success("✅ Request submitted successfully!")

    elif menu == "Dashboard":
        dashboard_option = st.radio("Select View", ["Tanker Purchase Summary", "Ticket Status"])

        data = sheet.get_all_values()
        if len(data) < 2:
            st.info("No data available yet.")
            return

        df = pd.DataFrame(data[1:], columns=data[0])
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")

        if dashboard_option == "Tanker Purchase Summary":
            st.subheader("🚰 Tanker Purchase Summary (Month-wise)")
            df["Month"] = df["Timestamp"].dt.strftime("%b %Y")
            tanker_summary = df.groupby(["Kitchen", "Month"]).size().reset_index(name="Tanker Purchased")
            st.dataframe(tanker_summary)
            st.bar_chart(
                tanker_summary.pivot(index="Month", columns="Kitchen", values="Tanker Purchased").fillna(0)
            )

        elif dashboard_option == "Ticket Status":
            st.subheader("🎫 Ticket Status")

            # Filters
            kitchen_filter = st.selectbox("Filter by Kitchen", options=["All"] + sorted(df["Kitchen"].unique().tolist()))
            date_filter = st.date_input("Filter by Date", value=None)

            filtered_df = df.copy()
            if kitchen_filter != "All":
                filtered_df = filtered_df[filtered_df["Kitchen"] == kitchen_filter]
            if date_filter:
                filtered_df = filtered_df[filtered_df["Timestamp"].dt.date == date_filter]

            st.dataframe(filtered_df)

    elif menu == "Admin Dashboard":
        is_admin_user, admin_name = is_admin()
        if not is_admin_user:
            st.warning("🔒 Please enter correct admin password.")
            return
        if not admin_name.strip():
            st.warning("Please enter your name/email in the sidebar to access Admin Dashboard.")
            return

        admin_menu = st.sidebar.radio("Admin Panel", ["Pending Requests", "All Requests"])
        data = sheet.get_all_values()
        if len(data) < 2:
            st.info("No requests found.")
            return

        df = pd.DataFrame(data[1:], columns=data[0])

        if admin_menu == "Pending Requests":
            filtered_df = df[df["Status"] == "Pending"]
            st.subheader("🕒 Pending Requests")
        else:
            filtered_df = df.copy()
            st.subheader("📋 All Requests")

        kitchen_filter = st.selectbox("Filter by Kitchen", options=["All"] + sorted(filtered_df["Kitchen"].unique().tolist()))
        status_filter = st.selectbox("Filter by Status", options=["All"] + sorted(filtered_df["Status"].unique().tolist()))
        search_text = st.text_input("Search by Employee Name or ID")

        if kitchen_filter != "All":
            filtered_df = filtered_df[filtered_df["Kitchen"] == kitchen_filter]
        if status_filter != "All":
            filtered_df = filtered_df[filtered_df["Status"] == status_filter]
        if search_text.strip():
            filtered_df = filtered_df[
                filtered_df["Employee Name"].str.contains(search_text, case=False, na=False) |
                filtered_df["Employee ID"].str.contains(search_text, case=False, na=False)
            ]

        if filtered_df.empty:
            st.info("No matching requests found.")
            return

        for i, row in filtered_df.iterrows():
            st.markdown("---")
            try:
                request_time = datetime.strptime(row["Timestamp"], "%Y-%m-%d %H:%M:%S")
                request_time_str = request_time.strftime("%d %b %Y, %I:%M %p")
            except Exception:
                request_time_str = row["Timestamp"]

            st.write(f"**Request Time:** {request_time_str}")
            st.write(f"**Kitchen:** {row['Kitchen']}  |  **Employee:** {row['Employee Name']} ({row['Employee ID']})  |  **Status:** {row['Status']}")

            st.markdown(f"""
                <a href="{row['Photo URL']}" target="_blank" style="
                    display: inline-block; 
                    background-color: #4CAF50; 
                    color: white; 
                    padding: 6px 12px; 
                    text-align: center; 
                    text-decoration: none; 
                    border-radius: 4px;">
                    Preview Image
                </a>
            """, unsafe_allow_html=True)

            try:
                st.image(row["Photo URL"], width=200)
            except:
                st.write("⚠️ Image preview failed.")

            col1, col2, col3 = st.columns([1,1,4])
            with col1:
                if st.button(f"Approve {i}", key=f"approve_{i}"):
                    sheet.update_cell(i + 2, 6, "Approved")
                    sheet.update_cell(i + 2, 7, admin_name)
                    st.success(f"Request {i+1} Approved")
            with col2:
                if st.button(f"Reject {i}", key=f"reject_{i}"):
                    sheet.update_cell(i + 2, 6, "Rejected")
                    sheet.update_cell(i + 2, 7, admin_name)
                    st.success(f"Request {i+1} Rejected")
            with col3:
                comment = st.text_area(f"Add Comment (optional) for request {i+1}", value=row["Comments"], key=f"comment_{i}")
                if st.button(f"Save Comment {i}", key=f"save_comment_{i}"):
                    sheet.update_cell(i + 2, 8, comment)
                    st.success("Comment saved.")

if __name__ == "__main__":
    main()
