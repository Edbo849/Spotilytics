import logging
import math

logger = logging.getLogger(__name__)


def generate_chartjs_line_graph(date_labels, datasets, x_label="Date", fill_area=False):
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
        fill_gradient = (
            {
                "target": "origin",
                "above": "rgba(29, 185, 84, 0.2)",
                "below": "rgba(29, 185, 84, 0.0)",
            }
            if fill_area
            else False
        )
        chart_datasets.append(
            {
                "label": dataset["label"],
                "data": dataset["data"],
                "fill": fill_gradient,
                "borderColor": dataset.get("color", "#1DB954"),
                "backgroundColor": dataset.get("color", "#1DB954"),
                "pointBackgroundColor": dataset.get("color", "#1DB954"),
                "pointBorderColor": dataset.get("color", "#1DB954"),
                "pointHoverBackgroundColor": dataset.get("color", "#1DB954"),
                "pointHoverBorderColor": "#fff",
                "borderWidth": 2,
                "pointRadius": 4,
                "pointHoverRadius": 6,
                "tension": 0.4,
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
                    "borderRadius": 10,
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
                        "color": "#ffffff",
                        "backdropColor": "rgba(0, 0, 0, 0)",
                        "callback": "function(value) { return value.toFixed(3); }",
                    },
                    "grid": {"display": True, "color": "#333"},
                    "angleLines": {
                        "display": True,
                        "color": "rgba(255, 255, 255, 0.1)",
                        "lineWidth": 0.5,
                    },
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
                        "size": 9,
                        "weight": "bold",
                    },
                    "textAlign": "center",
                    "rotation": 0,
                },
            },
        },
    }


def generate_chartjs_polar_area_chart(data):
    hours = [f"{i:02d}:00" for i in range(24)]
    max_value = max(data) * 1.05

    return {
        "type": "polarArea",
        "data": {
            "labels": hours,
            "datasets": [
                {
                    "data": data,
                    "backgroundColor": ["#1DB954"] * 24,
                    "borderWidth": 0,
                    "spacing": 5,
                }
            ],
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "scales": {
                "r": {
                    "ticks": {
                        "display": False,
                    },
                    "pointLabels": {
                        "display": "function(context) { return [0, 6, 12, 18].includes(context.index); }",
                        "font": {
                            "size": 12,
                            "weight": "bold",
                        },
                        "color": "#9e9e9e",
                    },
                    "min": 0,
                    "max": max_value,
                }
            },
            "plugins": {
                "legend": {"display": False},
                "datalabels": {"display": False},
            },
            "elements": {
                "arc": {
                    "borderRadius": 5,
                }
            },
        },
    }


def generate_chartjs_bubble_chart(data):
    """Generate bubble chart showing popularity vs. listening time vs. play count."""

    color_palette = [
        "rgba(29, 185, 84, 0.6)",
        "rgba(75, 192, 192, 0.6)",
        "rgba(255, 159, 64, 0.6)",
        "rgba(255, 99, 132, 0.6)",
        "rgba(54, 162, 235, 0.6)",
        "rgba(153, 102, 255, 0.6)",
        "rgba(201, 203, 207, 0.6)",
        "rgba(255, 205, 86, 0.6)",
        "rgba(139, 69, 19, 0.6)",
        "rgba(255, 105, 180, 0.6)",
    ]

    max_minutes = max(d["y"] for d in data)
    min_minutes = min(d["y"] for d in data)
    max_radius = max(d["r"] for d in data)

    base_min = math.floor(min_minutes / 100) * 100
    base_max = math.ceil(max_minutes / 100) * 100

    scaled_data = []
    for point in data:
        scaled_point = point.copy()
        scaled_point["r"] = (point["r"] / max_radius) * 30
        scaled_data.append(scaled_point)

    datasets = []
    for i, point in enumerate(scaled_data):
        datasets.append(
            {
                "label": point["name"],
                "data": [point],
                "backgroundColor": color_palette[i % len(color_palette)],
                "borderColor": color_palette[i % len(color_palette)].replace(
                    "0.6", "1"
                ),
                "borderWidth": 1,
                "hoverBackgroundColor": color_palette[i % len(color_palette)].replace(
                    "0.6", "0.8"
                ),
                "hoverBorderColor": "#fff",
            }
        )

    return {
        "type": "bubble",
        "data": {"datasets": datasets},
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "scales": {
                "x": {
                    "title": {
                        "display": True,
                        "text": "Popularity",
                        "color": "#9e9e9e",
                    },
                    "min": 0,
                    "max": 100,
                    "grid": {"color": "rgba(255, 255, 255, 0.1)", "drawBorder": False},
                    "ticks": {
                        "color": "#9e9e9e",
                        "stepSize": 20,
                    },
                },
                "y": {
                    "title": {
                        "display": True,
                        "text": "Minutes Played",
                        "color": "#9e9e9e",
                    },
                    "min": base_min,
                    "max": base_max,
                    "grid": {"color": "rgba(255, 255, 255, 0.1)", "drawBorder": False},
                    "ticks": {
                        "color": "#9e9e9e",
                        "stepSize": 100,
                    },
                },
            },
            "plugins": {
                "legend": {
                    "display": True,
                    "position": "top",
                    "labels": {
                        "color": "#9e9e9e",
                        "font": {"size": 10},
                    },
                },
                "datalabels": {
                    "display": False,
                },
            },
        },
    }


def generate_chartjs_stacked_bar_chart(labels, datasets):
    """Generate Chart.js data structure for a stacked bar chart."""

    color_palette = [
        "rgba(29, 185, 84, 0.8)",
        "rgba(255, 99, 132, 0.8)",
        "rgba(54, 162, 235, 0.8)",
        "rgba(255, 206, 86, 0.8)",
        "rgba(153, 102, 255, 0.8)",
        "rgba(75, 192, 192, 0.8)",
        "rgba(255, 159, 64, 0.8)",
        "rgba(231, 233, 237, 0.8)",
        "rgba(169, 50, 38, 0.8)",
        "rgba(82, 190, 128, 0.8)",
    ]

    for i, dataset in enumerate(datasets):
        dataset["backgroundColor"] = color_palette[i % len(color_palette)]

    return {
        "type": "bar",
        "data": {"labels": labels, "datasets": datasets},
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "scales": {
                "x": {
                    "stacked": True,
                    "grid": {"color": "rgba(255,255,255,0.1)"},
                    "ticks": {"color": "#9e9e9e"},
                },
                "y": {
                    "stacked": True,
                    "grid": {"color": "rgba(255,255,255,0.1)"},
                    "ticks": {"color": "#9e9e9e"},
                    "title": {"display": True, "text": "Streams", "color": "#9e9e9e"},
                },
            },
            "plugins": {
                "legend": {"labels": {"color": "#9e9e9e", "font": {"size": 10}}},
                "datalabels": {"display": False},
            },
        },
    }
