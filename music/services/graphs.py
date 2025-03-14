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


def generate_chartjs_radar_chart(labels, radar_data, metrics_keys=None):
    """
    Generate Chart.js data structure for a radar chart.

    Args:
        labels: List of metric names
        radar_data: List of dictionaries containing radar chart data for each item
        metrics_keys: List of keys to extract from each radar_data item
    """
    if metrics_keys is None:
        metrics_keys = [
            "total_plays",
            "total_time",
            "unique_tracks",
            "variety",
            "average_popularity",
        ]

    datasets = []
    for item in radar_data:
        metrics_data = [item.get(key, 0) for key in metrics_keys]

        datasets.append(
            {
                "label": item.get("label", "Unknown"),
                "data": metrics_data,
                "fill": True,
                "backgroundColor": item.get(
                    "backgroundColor", "rgba(29, 185, 84, 0.2)"
                ),
                "borderColor": item.get("borderColor", "#1DB954"),
                "pointBackgroundColor": item.get("borderColor", "#1DB954"),
                "pointBorderColor": "#fff",
                "pointHoverBackgroundColor": "#fff",
                "pointHoverBorderColor": item.get("borderColor", "#1DB954"),
            }
        )

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
                "datalabels": {
                    "display": False,
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

    # Handle case when data is not a list or is empty
    if not data or not isinstance(data, list):
        # Return empty chart configuration
        return {
            "type": "bubble",
            "data": {"datasets": []},
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
                        "grid": {
                            "color": "rgba(255, 255, 255, 0.1)",
                            "drawBorder": False,
                        },
                        "ticks": {"color": "#9e9e9e", "stepSize": 20},
                    },
                    "y": {
                        "title": {
                            "display": True,
                            "text": "Minutes Played",
                            "color": "#9e9e9e",
                        },
                        "min": 0,
                        "max": 100,
                        "grid": {
                            "color": "rgba(255, 255, 255, 0.1)",
                            "drawBorder": False,
                        },
                        "ticks": {"color": "#9e9e9e", "stepSize": 20},
                    },
                },
                "plugins": {
                    "legend": {
                        "display": True,
                        "position": "top",
                        "labels": {"color": "#9e9e9e", "font": {"size": 10}},
                    },
                    "datalabels": {"display": False},
                },
            },
        }

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

    max_minutes = max((d.get("y", 0) for d in data), default=100)
    min_minutes = min((d.get("y", 0) for d in data), default=0)
    max_radius = max((d.get("r", 0) for d in data), default=10)

    base_min = math.floor(min_minutes / 100) * 100
    base_max = math.ceil(max_minutes / 100) * 100

    scaled_data = []
    for point in data:
        if not isinstance(point, dict):
            continue

        scaled_point = point.copy()
        scaled_point["r"] = (
            (point.get("r", 5) / max_radius) * 30 if max_radius > 0 else 5
        )
        scaled_data.append(scaled_point)

    datasets = []
    for i, point in enumerate(scaled_data):
        datasets.append(
            {
                "label": point.get("name", f"Item {i+1}"),
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
                    "ticks": {"color": "#9e9e9e", "stepSize": 20},
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
                    "ticks": {"color": "#9e9e9e", "stepSize": 100},
                },
            },
            "plugins": {
                "legend": {
                    "display": True,
                    "position": "top",
                    "labels": {"color": "#9e9e9e", "font": {"size": 10}},
                },
                "datalabels": {"display": False},
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


def generate_chartjs_bar_chart(labels, values, y_label="Hours"):
    """Generate Chart.js bar chart for replay gaps."""
    return {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": "Average Hours Between Replays",
                    "data": values,
                    "backgroundColor": "rgba(29, 185, 84, 0.8)",
                    "borderColor": "rgba(29, 185, 84, 1.0)",
                    "borderWidth": 1,
                }
            ],
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "scales": {
                "y": {
                    "beginAtZero": True,
                    "title": {"display": True, "text": y_label, "color": "#9e9e9e"},
                    "grid": {"color": "rgba(255,255,255,0.1)"},
                    "ticks": {"color": "#9e9e9e"},
                },
                "x": {
                    "grid": {"color": "rgba(255,255,255,0.1)"},
                    "ticks": {
                        "color": "#9e9e9e",
                        "maxRotation": 45,
                        "minRotation": 45,
                        "font": {"size": 10},
                    },
                },
            },
            "plugins": {
                "legend": {"labels": {"color": "#9e9e9e", "font": {"size": 10}}},
                "datalabels": {"display": False},
            },
        },
    }


# music/utils/graphs.py


def generate_listening_context_chart(data):
    """Create a chart showing when an item is typically played."""

    colors = [
        "rgba(75, 192, 192, 0.7)",  # Night - Teal
        "rgba(255, 206, 86, 0.7)",  # Morning - Yellow
        "rgba(54, 162, 235, 0.7)",  # Afternoon - Blue
        "rgba(255, 99, 132, 0.7)",  # Evening - Red
    ]

    hover_colors = [
        "rgba(75, 192, 192, 1)",
        "rgba(255, 206, 86, 1)",
        "rgba(54, 162, 235, 1)",
        "rgba(255, 99, 132, 1)",
    ]

    return {
        "type": "bar",
        "data": {
            "labels": data["labels"],
            "datasets": [
                {
                    "label": "Plays",
                    "data": data["values"],
                    "backgroundColor": colors,
                    "hoverBackgroundColor": hover_colors,
                    "borderColor": "rgba(255, 255, 255, 0.2)",
                    "borderWidth": 1,
                }
            ],
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "indexAxis": "y",  # Horizontal bar chart
            "scales": {
                "x": {
                    "beginAtZero": True,
                    "grid": {"color": "rgba(255, 255, 255, 0.1)"},
                    "ticks": {"color": "#9e9e9e", "font": {"size": 12}},
                },
                "y": {
                    "grid": {"color": "rgba(255, 255, 255, 0.1)"},
                    "ticks": {"color": "#9e9e9e", "font": {"size": 12}},
                },
            },
            "plugins": {
                "tooltip": {
                    "callbacks": {
                        "afterLabel": "function(context) { "
                        + "return ["
                        + ", ".join([f"'{x}'" for x in data["contexts"]])
                        + "][context.dataIndex] + ' - ' + ["
                        + ", ".join([str(x) for x in data["percentages"]])
                        + "][context.dataIndex] + '%'; }"
                    }
                },
                "legend": {"display": False},
                "datalabels": {
                    "display": True,
                    "align": "end",
                    "anchor": "end",
                    "color": "#ffffff",
                    "font": {"size": 14, "weight": "bold"},
                    "formatter": "function(value, context) { "
                    + "return ["
                    + ", ".join([str(x) for x in data["percentages"]])
                    + "][context.dataIndex] + '%'; }",
                },
            },
        },
    }


def generate_gauge_chart(data, title="Coverage"):
    """Create a proper gauge chart showing percentage metrics with fallback."""
    # Extract percentage value from data
    if isinstance(data, dict):
        percentage = data["percentage"]
        played_count = data.get("played_count", 0)
        total_count = data.get("total_count", 0)
    else:
        percentage = float(data)
        played_count = 0
        total_count = 0

    subtitle_text = (
        f"{played_count}/{total_count}"
        if played_count and total_count
        else f"{percentage:.1f}%"
    )

    return {
        "type": "doughnut",
        "data": {
            "datasets": [
                {
                    "data": [percentage, 100 - percentage],
                    "backgroundColor": [
                        "rgba(29, 185, 84, 0.8)",
                        "rgba(220, 220, 220, 0.2)",
                    ],
                    "borderWidth": 0,
                }
            ]
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "circumference": 180,
            "rotation": 270,
            "cutout": "60%",
            "layout": {
                "padding": {
                    "top": 20,
                    "bottom": 40,
                    "left": 40,
                    "right": 40,
                }
            },
            "plugins": {
                "tooltip": {
                    "enabled": False,
                },
                "legend": {
                    "display": False,
                },
                "title": {
                    "display": True,
                    "text": title,
                    "padding": 20,
                    "font": {"size": 16},
                },
                "subtitle": {
                    "display": True,
                    "text": subtitle_text,
                    "padding": {"bottom": 20},
                    "font": {"size": 20, "weight": "bold"},
                    "color": "#1DB954",
                },
                "datalabels": {
                    "display": False,
                },
            },
            # This custom JavaScript function will be executed in the frontend
            # to draw text in the center of the semi-circle
            "afterDraw": "function(chart) { "
            + "  const ctx = chart.ctx;"
            + "  const centerX = (chart.chartArea.left + chart.chartArea.right) / 2;"
            + "  let centerY = (chart.chartArea.top + chart.chartArea.bottom) / 2;"
            + "  centerY = centerY + chart.chartArea.bottom * 0.1;"
            + "  ctx.save();"
            + "  ctx.fillStyle = '#FFFFFF';"
            + "  ctx.font = 'bold 24px Arial';"
            + "  ctx.textAlign = 'center';"
            + "  ctx.textBaseline = 'middle';"
            + f"  ctx.fillText('{percentage:.1f}%', centerX, centerY);"
            + "  ctx.restore();"
            + "}",
        },
    }


def generate_progress_chart(data):
    """Create a progress bar comparing average duration to track duration."""
    percentage_formatted = f"{data['percentage'] * 100:.1f}"

    return {
        "type": "bar",
        "data": {
            "labels": ["Listen Duration"],
            "datasets": [
                {
                    "label": "Average Listen",
                    "data": [data["average_duration"]],
                    "backgroundColor": "rgba(75, 192, 192, 0.6)",
                },
                {
                    "label": "Full Track",
                    "data": [data["track_duration"]],
                    "backgroundColor": "rgba(220, 220, 220, 0.6)",
                },
            ],
        },
        "options": {
            "indexAxis": "y",
            "scales": {
                "x": {
                    "beginAtZero": True,
                    "title": {"display": True, "text": "Duration (seconds)"},
                }
            },
            "plugins": {
                "title": {"display": True, "text": "Average Listening Duration"},
                "subtitle": {
                    "display": True,
                    "text": f"{percentage_formatted}% of track typically played",
                },
            },
        },
    }


def generate_horizontal_bar_chart(data):
    """Create a horizontal bar chart showing plays for every track."""
    return {
        "type": "bar",
        "data": {
            "labels": data["labels"],
            "datasets": [
                {
                    "label": "Plays",
                    "data": data["values"],
                    "backgroundColor": "rgba(54, 162, 235, 0.6)",
                    "borderColor": "rgba(54, 162, 235, 1)",
                    "borderWidth": 1,
                }
            ],
        },
        "options": {
            "indexAxis": "y",
            "scales": {
                "x": {"beginAtZero": True, "ticks": {"precision": 0}},
                "y": {
                    "ticks": {
                        "font": {"size": 9},
                        "maxRotation": 0,
                        "minRotation": 0,
                    }
                },
            },
            "maintainAspectRatio": False,
        },
    }
