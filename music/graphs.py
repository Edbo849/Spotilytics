import logging

logger = logging.getLogger(__name__)


def generate_chartjs_line_graph(date_labels, datasets, x_label="Date"):
    """
    Generates data for a Chart.js line graph with multiple datasets.

    Args:
        date_labels (list): List of date labels for x-axis
        datasets (list): List of dictionaries containing dataset info:
                        [{'label': 'Name', 'data': [counts], 'color': '#hex'}]
        x_label (str): Label for x-axis

    Returns:
        dict: Chart.js compatible data structure
    """

    chart_datasets = []
    for dataset in datasets:
        chart_datasets.append(
            {
                "label": dataset["label"],
                "data": dataset["data"],
                "fill": False,
                "borderColor": dataset.get("color", "#1DB954"),
                "backgroundColor": dataset.get("color", "#1DB954"),
                "pointBackgroundColor": dataset.get("color", "#1DB954"),
                "pointBorderColor": dataset.get("color", "#1DB954"),
                "pointHoverBackgroundColor": dataset.get("color", "#1DB954"),
                "pointHoverBorderColor": "#fff",
                "borderWidth": 2,
                "pointRadius": 4,
                "pointHoverRadius": 6,
            }
        )

    chart_data = {"labels": date_labels, "datasets": chart_datasets}
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


def generate_chartjs_radar_chart(labels, radar_data):
    """
    Generate Chart.js data structure for a radar chart.

    Args:
        labels: List of metric names
        radar_data: List of dictionaries containing radar chart data for each item
    """
    datasets = [
        {
            "label": item["label"],
            "data": [
                item["total_plays"],
                item["total_time"],
                item["unique_tracks"],
                item["variety"],
                item["average_popularity"],
            ],
            "fill": True,
            "backgroundColor": item["backgroundColor"],
            "borderColor": item["borderColor"],
            "pointBackgroundColor": item["borderColor"],
            "pointBorderColor": "#fff",
            "pointHoverBackgroundColor": "#fff",
            "pointHoverBorderColor": item["borderColor"],
        }
        for item in radar_data
    ]

    return {
        "type": "radar",
        "data": {
            "labels": labels,
            "datasets": datasets,
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "scales": {
                "r": {
                    "angleLines": {
                        "display": True,
                        "color": "rgba(255,255,255,0.1)",
                    },
                    "grid": {
                        "color": "rgba(255,255,255,0.1)",
                    },
                    "pointLabels": {
                        "color": "#9e9e9e",
                    },
                    "ticks": {
                        "beginAtZero": True,
                        "color": "#ffffff",
                        "backdropColor": "rgba(0, 0, 0, 0)",
                        "min": 0,
                    },
                },
            },
            "plugins": {
                "legend": {
                    "labels": {
                        "color": "#9e9e9e",
                    },
                },
            },
        },
    }


def generate_chartjs_doughnut_chart(labels, data, background_colors):
    return {
        "type": "doughnut",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "data": data,
                    "backgroundColor": background_colors,
                }
            ],
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "legend": {
                    "display": False,
                },
                "datalabels": {
                    "display": True,
                    "color": "#ffffff",
                    "font": {
                        "size": 9,  # Reduced from 11
                        "weight": "bold",
                    },
                    "textAlign": "center",
                    "rotation": 0,
                },
            },
        },
    }
