import streamlit as st
import pandas as pd
import re
from io import BytesIO
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import Font

# Function to save DataFrame to Excel with bold headers and additional stats
def to_excel_with_bold_and_stats(df, start_date=None, end_date=None):
    output = BytesIO()
    wb = Workbook()
    ws = wb.active
    
    # Write DataFrame rows
    for i, row in enumerate(dataframe_to_rows(df, index=False, header=True)):
        ws.append(row)
        if i == 0:  # Bold headers
            for cell in ws[i + 1]:
                cell.font = Font(bold=True)
    
    # Calculate stats
    if start_date and end_date:
        total_days = (end_date - start_date).days + 1  # Calculate total days from start to end date
    else:
        total_days = "N/A"

    avg_column_f = df.iloc[:, 5].mean() if len(df.columns) > 5 else "N/A"  # Average of column F if it exists

    # Append stats at the end
    ws.append([])  # Empty row for separation
    ws.append(["Total Days:", total_days])  # Total days in column A
    ws.append(["Average of Column F:", avg_column_f])  # Average in column F
    
    # Save workbook to bytes
    wb.save(output)
    return output.getvalue()

# Function to create the adjusted filled DataFrame based on the specified start and end dates
def create_adjusted_filled_dataframe(meter_data, start_date, end_date, date_column, avg_day_column):
    # Convert start_date and end_date to pandas datetime
    start_date = pd.to_datetime(start_date)
    end_date = pd.to_datetime(end_date)

    filtered_data = meter_data[meter_data[date_column] > start_date]
    
    if not filtered_data.empty:
        # Calculate the days difference
        days_difference = (filtered_data.iloc[0, 0] - start_date).days + 1  # Include the start date
        meter_data.loc[filtered_data.index[0], meter_data.columns[2]] = days_difference
        meter_data.loc[filtered_data.index[0], meter_data.columns[-1]] = (
            meter_data.loc[filtered_data.index[0], meter_data.columns[-2]] / days_difference
        )

    # Create an empty DataFrame with all dates in the range
    all_dates = pd.date_range(start=start_date, end=end_date, freq='D')
    filled_data = pd.DataFrame({date_column: all_dates})

    # Merge the meter data with all dates
    filled_data = pd.merge(filled_data, meter_data, on=date_column, how='left')
    last_filled_date = -1

    # Forward-fill only from the closest next available reading after the start date
    for i in range(len(filled_data)):
        if pd.isna(filled_data.iloc[i][avg_day_column]):
            future_values = meter_data[meter_data[date_column] > filled_data.iloc[i][date_column]]
            if not future_values.empty and (future_values.iloc[0, 0] <= filled_data.iloc[-1, 0]):
                filled_data.iloc[i, 2:] = future_values.iloc[0, 2:]
            else:
                if last_filled_date == -1:
                    last_filled_date = end_date
                filled_data.iloc[i, 2] = (end_date - last_filled_date).days + 1  # Include start date
                filled_data.iloc[i, 3:] = 0
        else:
            last_filled_date = filled_data.iloc[i][date_column]

    return filled_data

# Step 1: Upload and process the raw data file
st.title("Meter Readings Processor")

# File upload
uploaded_file = st.file_uploader("Upload the raw data file (Excel format)", type=["xlsx"])

if uploaded_file:
    # Load the raw data file
    raw_data = pd.read_excel(uploaded_file)

    # Drop columns that are completely empty (all values are NaN)
    raw_data_cleaned = raw_data.dropna(axis=1, how='all')

    # Identify the date column (assuming it's the first column)
    date_column = raw_data_cleaned.columns[0]

    # Ensure the date column is in datetime format
    raw_data_cleaned[date_column] = pd.to_datetime(raw_data_cleaned[date_column], errors='coerce')

    # Filter out columns that contain 'reading' (case-insensitive) to select only the reading columns for each meter
    reading_columns = [col for col in raw_data_cleaned.columns if 'reading' in col.lower()]

    # Create a new DataFrame with only the date and reading columns
    filtered_data = raw_data_cleaned[[date_column] + reading_columns]

    filtered_data[date_column] = pd.to_datetime(filtered_data[date_column])
    
    # Keep only the date part
    filtered_data[date_column] = filtered_data[date_column].dt.date

    # Drop rows where all reading columns are NaN to only keep rows with at least one recorded reading
    filtered_data = filtered_data.dropna(subset=reading_columns, how='all')

    # Calculate the date range
    start_date = filtered_data[date_column].min()
    end_date = filtered_data[date_column].max()

    # Download option for filtered data
    if st.button("Download Filtered Data"):
        filtered_excel = to_excel_with_bold_and_stats(filtered_data, start_date=start_date, end_date=end_date)
        st.download_button(
            label="Download Filtered Data",
            data=filtered_excel,
            file_name="Filtered_Meter_Readings.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    # Step 2: Select a meter and generate detailed readings
    st.write("Now select a meter for detailed analysis.")
    meter_name = st.selectbox("Select a meter", filtered_data.columns[1:])

    if meter_name:
        meter_data = filtered_data[[date_column, meter_name]].dropna(subset=[meter_name])
        meter_data = meter_data.sort_values(by=date_column).reset_index(drop=True)
        meter_data[date_column] = pd.to_datetime(meter_data[date_column], errors='coerce')

        # Step 3: Calculate days since the previous reading
        meter_data['Days Since Previous Reading'] = meter_data[date_column].diff().dt.days.fillna(method='bfill').astype(int)

        # Step 4: Calculate delta m³
        meter_data['Delta m³'] = meter_data[meter_name].diff().fillna(method='bfill')

        # Step 5: Calculate m³ per Acre
        plot_size = st.number_input("Enter the plot size in acres for this meter:", min_value=0.01)
        if plot_size > 0:
            meter_data['m³ per Acre'] = meter_data['Delta m³'] / plot_size

            # Step 6: Calculate m³ per Acre per Avg Day
            meter_data['m³ per Acre per Avg Day'] = meter_data['m³ per Acre'] / meter_data['Days Since Previous Reading'].replace(0, 1)

            # Step 7: Specify Date Range
            st.subheader("Step 7: Specify Date Range")
            start_date = st.date_input("Start Date")
            end_date = st.date_input("End Date")

            # Forward-filled data based on the adjusted logic
            if st.button("Download Filled Data with Forward-Filled m³ per Acre per Avg Day"):
                filled_data = create_adjusted_filled_dataframe(
                    meter_data=meter_data.copy(),
                    start_date=start_date,
                    end_date=end_date,
                    date_column=date_column,
                    avg_day_column='m³ per Acre per Avg Day'
                )
                filled_excel = to_excel_with_bold_and_stats(filled_data, start_date=start_date, end_date=end_date)
                st.download_button(
                    label="Download Filled Data",
                    data=filled_excel,
                    file_name="Adjusted_Filled_Meter_Readings.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )