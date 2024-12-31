import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def generate_chartjs_line_graph(date_labels, counts, x_label="Date"):
    """
    Generates data for a Chart.js line graph.

    Args:
        date_labels (list): List of date labels for x-axis
        counts (list): List of count values for y-axis
        x_label (str): Label for x-axis

    Returns:
        dict: Chart.js compatible data structure
    """

    if x_label.lower() == "month":
        date_format = "%m-%Y"
    elif x_label.lower() == "year":
        date_format = "%Y"
    else:
        date_format = "%d-%m-%Y"

    formatted_labels = [
        datetime.strptime(date, "%Y-%m-%d").strftime(date_format)
        for date in date_labels
    ]

    chart_data = {
        "labels": formatted_labels,
        "datasets": [
            {
                "label": "Number of Songs",
                "data": counts,
                "fill": False,
                "borderColor": "#1DB954",
                "backgroundColor": "#1DB954",
                "pointBackgroundColor": "#1DB954",
                "pointBorderColor": "#1DB954",
                "pointHoverBackgroundColor": "#1DB954",
                "pointHoverBorderColor": "#fff",
                "borderWidth": 2,
                "pointRadius": 4,
                "pointHoverRadius": 6,
            }
        ],
    }
    return chart_data


def generate_chartjs_pie_chart(labels, values):
    """Generate Chart.js data structure for a polar area chart with centered point labels."""
    sorted_data = sorted(zip(labels, values), key=lambda x: x[0])
    labels, values = zip(*sorted_data) if sorted_data else ([], [])

    chart_data = {
        "type": "polarArea",
        "legend": {"display": False},
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "data": values,
                    "backgroundColor": ["#1DB954"] * len(labels),
                    "borderColor": "black",
                    "borderWidth": 0.1,
                    "spacing": 3,
                }
            ],
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "legend": {"display": False},
            "scales": {
                "r": {
                    "ticks": {
                        "display": True,
                        "color": "#9e9e9e",
                        "backdropColor": "rgba(0, 0, 0, 0)",
                    },
                    "grid": {"display": True, "color": "#333"},
                    "angleLines": {"display": False},
                    "pointLabels": {
                        "display": True,
                        "centerPointLabels": True,
                        "font": {"size": 10, "family": "Arial"},
                        "color": "white",
                    },
                }
            },
            "plugins": {
                "tooltip": {
                    "enabled": True,
                },
                "legend": {"display": False},
            },
        },
    }
    return chart_data
