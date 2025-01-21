import streamlit as st
import pandas as pd
from io import BytesIO

def scan_for_errors(df, meter_col):
    """
    Scan the specified meter column for errors where a reading decreases.
    Returns the row index where the error occurs and the previous valid value.
    """
    prev_value = None
    second_prev = None
    prev_idx = None
    count = 0
    for idx, value in df[meter_col].items():
        if pd.notna(value):  # Skip NaN values
            count+=1
            if prev_value is not None and value < prev_value:
                return idx, prev_value, count, second_prev, prev_idx
            second_prev= prev_value
            prev_value = value
            prev_idx= idx
    return None, None, None, None, None

def update_value(df, meter_col, date, new_value, prev_idx, new_value2):
    """
    Update the specified value in the DataFrame.
    """
    df.loc[df['start'] == date, meter_col] = new_value
    if prev_idx!=None:
        df.loc[prev_idx, meter_col] = new_value2

# Streamlit UI
st.title("Meter Data Error Fixing Tool")
st.write("Upload your Excel file to scan and fix errors in meter readings.")

uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    st.write("Uploaded Data Preview:")
    
    # Get the list of meter columns (assumes first column is 'start')
    meter_columns = df.columns[1:]
    session_key = "current_error"  # Unique session state key

    # Initialize session state for tracking progress
    if session_key not in st.session_state:
        st.session_state[session_key] = {"meter_col": None, "error_index": None, "error_fixed": False, "completed_columns": [], "df" : df}

    # State for current error
    current_state = st.session_state[session_key]
    df = current_state["df"]
    print(df)
    for meter_col in meter_columns:
        if meter_col in current_state["completed_columns"]:
            continue  # Skip already processed columns


        if current_state["meter_col"] is None:
            current_state["meter_col"] = meter_col

        if current_state["meter_col"] == meter_col:
            error_index, prev_value, count, second_prev, prev_idx = scan_for_errors(df, meter_col)
            st.write(f"Processing {meter_col}...")  # Debug statement to track progress

            if error_index is not None:
                # Detect if an error still exists after the previous submit
                current_error = df.iloc[error_index]
                st.write(f"Error found at {error_index} for {meter_col}")  # Debug statement

                if not current_state["error_fixed"]:
                    st.error(f"Error found in {meter_col}")

                    st.write(f"**Error Details**:")
                    st.write(f"- Date: {current_error['start']}")
                    st.write(f"- Value: {current_error[meter_col]}")
                    st.write(f"- Previous Reading: {prev_value}")
                    if(count!=2):
                        st.write(f"- Second last reading: {second_prev}")

                    # Form to fix the error
                    with st.form(key=f"fix_error_{meter_col}_{error_index}"):
                        new_value = st.number_input(
                            f"New Reading for {current_error['start']}",
                            value=float(current_error[meter_col]) if not pd.isna(current_error[meter_col]) else 0.0,
                        )

                        submit = st.form_submit_button("Submit")
                        ignore = st.form_submit_button("Ignore Error")
                        
                        if prev_idx!=None:
                            new_value2 = st.number_input(
                                f"New Reading for Previous Reading",
                                value=float(df.iloc[prev_idx][meter_col]) if not pd.isna(df.iloc[prev_idx][meter_col]) else 0.0,
                            )
                            submit = st.form_submit_button("Submit previous reading")
                        

                        if submit:
                            # Update the DataFrame with the corrected value
                            update_value(df, meter_col, current_error['start'], new_value, prev_idx, new_value2)
                            st.success(f"Updated reading for {meter_col} on {current_error['start']} to {new_value}")
                            # current_state["error_fixed"] = True  # Mark the error as fixed
                            st.session_state[session_key] = current_state  # Save the state
                            current_state["df"] = df
                            st.rerun()  # Trigger the rerun to refresh and check the next error

                        elif ignore:
                            st.warning("Error ignored. Moving to next error...")
                            # current_state["error_fixed"] = True
                            st.session_state[session_key] = current_state
                            current_state["df"] = df
                            st.rerun()  # Trigger rerun after ignoring the error

                # If the error was fixed, reset state to detect the next error
                elif current_state["error_fixed"]:
                    current_state["completed_columns"].append(meter_col)  # Add completed column to list
                    current_state["meter_col"] = None
                    current_state["error_index"] = None
                    current_state["error_fixed"] = False
                    current_state["df"] = df
                    st.session_state[session_key] = current_state
                    st.rerun()

                # Stop processing further errors until this one is resolved
                st.stop()

            else:
                st.success(f"All errors fixed for {meter_col}")
                # Mark the meter column as processed
                current_state["completed_columns"].append(meter_col)
                current_state["meter_col"] = None

    # Provide download link for corrected data
    corrected_file = BytesIO()
    df.to_excel(corrected_file, index=False, engine="openpyxl")
    corrected_file.seek(0)
    st.download_button(
        "Download Corrected File",
        data=corrected_file,
        file_name="corrected_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
