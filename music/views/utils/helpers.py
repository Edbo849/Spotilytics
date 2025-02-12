# Helper functions for Views


def get_x_label(time_range):
    x_label = "Date"
    if time_range == "last_7_days":
        x_label = "Date"
    elif time_range in ["last_4_weeks", "6_months"]:
        x_label = "Month"
    elif time_range in ["last_year", "all_time"]:
        x_label = "Year"
    return x_label
