import logging
import math

logger = logging.getLogger(__name__)


def generate_chartjs_line_graph(date_labels, datasets, x_label="Date", fill_area=False):
    """
    Generate data for a Chart.js line graph with multiple datasets.

    Args:
        date_labels: List of date labels for x-axis
        datasets: List of dictionaries containing dataset info:
                 [{'label': 'Name', 'data': [counts], 'color': '#hex'}]
        x_label: Label for x-axis
        fill_area: Whether to fill the area below the line

    Returns:
        Chart.js compatible data structure as a dictionary
    """
    fill_gradient = (
        {
            "target": "origin",
            "above": "rgba(29, 185, 84, 0.2)",
            "below": "rgba(29, 185, 84, 0.0)",
        }
        if fill_area
        else False
    )

    chart_datasets = []
    for dataset in datasets:
        color = dataset.get("color", "#1DB954")
        chart_datasets.append(
            {
                "label": dataset["label"],
                "data": dataset["data"],
                "fill": fill_gradient,
                "borderColor": color,
                "backgroundColor": color,
                "pointBackgroundColor": color,
                "pointBorderColor": color,
                "pointHoverBackgroundColor": color,
                "pointHoverBorderColor": "#fff",
                "borderWidth": 2,
                "pointRadius": 4,
                "pointHoverRadius": 6,
                "tension": 0.4,
            }
        )

    return {"labels": date_labels, "datasets": chart_datasets}


def generate_chartjs_pie_chart(labels, values):
    """
    Generate Chart.js data structure for a polar area chart with centered point labels.

    Args:
        labels: List of labels for pie segments
        values: List of values corresponding to labels

    Returns:
        Chart.js compatible data structure
    """
    if not labels or not values:
        return {"type": "polarArea", "data": {"labels": [], "datasets": [{"data": []}]}}

    sorted_data = sorted(zip(labels, values), key=lambda x: x[0])
    labels, values = zip(*sorted_data)

    return {
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
                        "color": "rgba(255, 255, 255, 0.6)",
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
                        "color": "rgba(255, 255, 255, 0.6)",
                    },
                }
            },
            "plugins": {
                "tooltip": {"enabled": True},
                "legend": {"display": False},
            },
        },
    }


def generate_chartjs_radar_chart(labels, radar_data, metrics_keys=None):
    """
    Generate Chart.js data structure for a radar chart.

    Args:
        labels: List of metric names
        radar_data: List of dictionaries containing radar chart data for each item
        metrics_keys: List of keys to extract from each radar_data item

    Returns:
        Chart.js compatible data structure
    """
    metrics_keys = metrics_keys or [
        "total_plays",
        "total_time",
        "unique_tracks",
        "variety",
        "average_popularity",
    ]

    datasets = []
    for item in radar_data:
        metrics_data = [item.get(key, 0) for key in metrics_keys]
        border_color = item.get("borderColor", "#1DB954")

        datasets.append(
            {
                "label": item.get("label", "Unknown"),
                "data": metrics_data,
                "fill": True,
                "backgroundColor": item.get(
                    "backgroundColor", "rgba(29, 185, 84, 0.2)"
                ),
                "borderColor": border_color,
                "pointBackgroundColor": border_color,
                "pointBorderColor": "#fff",
                "pointHoverBackgroundColor": "#fff",
                "pointHoverBorderColor": border_color,
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
                    "angleLines": {"display": True, "color": "rgba(255,255,255,0.1)"},
                    "grid": {"color": "rgba(255,255,255,0.1)"},
                    "pointLabels": {"color": "#9e9e9e"},
                    "ticks": {
                        "beginAtZero": True,
                        "color": "rgba(255, 255, 255, 0.6)",
                        "backdropColor": "rgba(0, 0, 0, 0)",
                        "min": 0,
                    },
                },
            },
            "plugins": {
                "legend": {"labels": {"color": "#9e9e9e"}},
                "datalabels": {"display": False},
            },
        },
    }


def generate_chartjs_doughnut_chart(labels, data, background_colors):
    """
    Generate Chart.js doughnut chart configuration.

    Args:
        labels: List of segment labels
        data: List of values for each segment
        background_colors: List of colors for each segment

    Returns:
        Chart.js compatible configuration
    """
    return {
        "type": "doughnut",
        "data": {
            "labels": labels,
            "datasets": [{"data": data, "backgroundColor": background_colors}],
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "legend": {
                    "display": True,
                    "labels": {
                        "color": "rgba(255, 255, 255, 0.6)",
                        "font": {"size": 12},
                    },
                },
                "datalabels": {
                    "display": True,
                    "color": "rgba(255, 255, 255, 0.6)",
                    "font": {"size": 9, "weight": "bold"},
                    "textAlign": "center",
                    "rotation": 0,
                },
            },
        },
    }


def generate_chartjs_polar_area_chart(data):
    """
    Generate Chart.js polar area chart showing hourly data distribution.

    Args:
        data: List of 24 values representing hourly data

    Returns:
        Chart.js compatible configuration
    """
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
                    "ticks": {"display": False},
                    "pointLabels": {
                        "display": "function(context) { return [0, 6, 12, 18].includes(context.index); }",
                        "font": {"size": 12, "weight": "bold"},
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
            "elements": {"arc": {"borderRadius": 5}},
        },
    }


def generate_chartjs_bubble_chart(data):
    """
    Generate bubble chart showing popularity vs. listening time vs. play count.

    Args:
        data: List of dictionaries with x, y, r values and metadata

    Returns:
        Chart.js compatible configuration
    """
    if not data or not isinstance(data, list):
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

    # Create datasets with scaled radius values
    datasets = []
    for i, point in enumerate(data):
        if not isinstance(point, dict):
            continue

        scaled_radius = (point.get("r", 5) / max_radius) * 30 if max_radius > 0 else 5
        color = color_palette[i % len(color_palette)]

        datasets.append(
            {
                "label": point.get("name", f"Item {i+1}"),
                "data": [{**point, "r": scaled_radius}],
                "backgroundColor": color,
                "borderColor": color.replace("0.6", "1"),
                "borderWidth": 1,
                "hoverBackgroundColor": color.replace("0.6", "0.8"),
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
    """
    Generate Chart.js data structure for a stacked bar chart.

    Args:
        labels: List of x-axis labels
        datasets: List of dataset objects

    Returns:
        Chart.js compatible configuration
    """
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
    """
    Generate Chart.js bar chart for replay gaps.

    Args:
        labels: List of x-axis labels
        values: List of values corresponding to labels
        y_label: Label for y-axis

    Returns:
        Chart.js compatible configuration
    """
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


def generate_listening_context_chart(data):
    """
    Create a chart showing when an item is typically played.

    Args:
        data: Dictionary containing context data

    Returns:
        Chart.js compatible configuration
    """
    colors = [
        "rgba(75, 192, 192, 0.7)",  # Night - Teal
        "rgba(255, 206, 86, 0.7)",  # Morning - Yellow
        "rgba(54, 162, 235, 0.7)",  # Afternoon - Blue
        "rgba(255, 99, 132, 0.7)",  # Evening - Red
    ]

    hover_colors = [color.replace("0.7", "1") for color in colors]

    # Format the callback function data as strings for contexts and percentages
    context_strings = [f"'{x}'" for x in data["contexts"]]
    percentage_strings = [str(x) for x in data["percentages"]]

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
                        "afterLabel": f"function(context) {{ "
                        f"return [{', '.join(context_strings)}][context.dataIndex] + ' - ' + "
                        f"[{', '.join(percentage_strings)}][context.dataIndex] + '%'; }}"
                    }
                },
                "legend": {"display": False},
                "datalabels": {
                    "display": True,
                    "align": "end",
                    "anchor": "end",
                    "color": "rgba(255, 255, 255, 0.6)",
                    "font": {"size": 14, "weight": "bold"},
                    "formatter": f"function(value, context) {{ "
                    f"return [{', '.join(percentage_strings)}][context.dataIndex] + '%'; }}",
                },
            },
        },
    }


def generate_gauge_chart(data, title="Coverage"):
    """
    Create a proper gauge chart showing percentage metrics with fallback.

    Args:
        data: Dictionary with percentage or direct percentage value
        title: Title for the chart

    Returns:
        Chart.js compatible configuration
    """
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
                "tooltip": {"enabled": False},
                "legend": {"display": False},
                "title": {
                    "display": True,
                    "text": title,
                    "padding": 20,
                    "font": {"size": 16},
                    "color": "rgba(255, 255, 255, 0.6)",
                },
                "subtitle": {
                    "display": True,
                    "text": subtitle_text,
                    "padding": {"bottom": 20},
                    "font": {"size": 20, "weight": "bold"},
                    "color": "#1DB954",
                },
                "datalabels": {"display": False},
            },
            # JavaScript function for center text
            "afterDraw": f"function(chart) {{ "
            f"  const ctx = chart.ctx;"
            f"  const centerX = (chart.chartArea.left + chart.chartArea.right) / 2;"
            f"  let centerY = (chart.chartArea.top + chart.chartArea.bottom) / 2;"
            f"  centerY = centerY + chart.chartArea.bottom * 0.1;"
            f"  ctx.save();"
            f"  ctx.fillStyle = '#FFFFFF';"
            f"  ctx.font = 'bold 24px Arial';"
            f"  ctx.textAlign = 'center';"
            f"  ctx.textBaseline = 'middle';"
            f"  ctx.fillText('{percentage:.1f}%', centerX, centerY);"
            f"  ctx.restore();"
            f"}}",
        },
    }


def generate_progress_chart(data):
    """
    Create a progress bar comparing average duration to track duration.

    Args:
        data: Dictionary containing track duration information

    Returns:
        Chart.js compatible configuration
    """
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
                    "title": {
                        "display": True,
                        "text": "Duration (seconds)",
                        "color": "rgba(255, 255, 255, 0.6)",
                    },
                    "ticks": {"color": "rgba(255, 255, 255, 0.6)"},
                },
                "y": {"ticks": {"color": "rgba(255, 255, 255, 0.6)"}},
            },
            "plugins": {
                "title": {
                    "display": True,
                    "text": "Average Listening Duration",
                    "color": "rgba(255, 255, 255, 0.6)",
                },
                "subtitle": {
                    "display": True,
                    "text": f"{percentage_formatted}% of track typically played",
                    "color": "rgba(255, 255, 255, 0.6)",
                },
                "legend": {"labels": {"color": "rgba(255, 255, 255, 0.6)"}},
            },
        },
    }


def generate_horizontal_bar_chart(data):
    """
    Create a horizontal bar chart showing plays for every track.

    Args:
        data: Dictionary containing labels and values

    Returns:
        Chart.js compatible configuration
    """
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
                "x": {
                    "beginAtZero": True,
                    "ticks": {"precision": 0, "color": "rgba(255, 255, 255, 0.6)"},
                    "title": {
                        "display": True,
                        "text": "Plays",
                        "color": "rgba(255, 255, 255, 0.6)",
                    },
                    "grid": {"color": "rgba(255, 255, 255, 0.1)"},
                },
                "y": {
                    "ticks": {
                        "font": {"size": 9},
                        "maxRotation": 0,
                        "minRotation": 0,
                        "color": "rgba(255, 255, 255, 0.6)",
                    },
                    "grid": {"color": "rgba(255, 255, 255, 0.1)"},
                },
            },
            "maintainAspectRatio": False,
            "plugins": {"legend": {"labels": {"color": "rgba(255, 255, 255, 0.6)"}}},
        },
    }
