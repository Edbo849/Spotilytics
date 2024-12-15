import logging

import plotly.graph_objects as go

logger = logging.getLogger(__name__)


def generate_plotly_line_graph(date_labels, counts, x_label="Date"):
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=date_labels,
            y=counts,
            mode="lines+markers",
            line=dict(color="#1DB954"),
            marker=dict(size=8),
            hovertemplate=f"{x_label}: %{{x}}<br>Songs: %{{y}}<extra></extra>",
        )
    )

    tickformat = {
        "Hour": "%Y-%m-%d %H:%M",
        "Day": "%Y-%m-%d",
        "Week": "%Y-%m-%d",
        "Month": "%Y-%m",
    }.get(x_label, "%Y-%m-%d")

    fig.update_layout(
        plot_bgcolor="#333333",
        paper_bgcolor="#333333",
        xaxis=dict(
            title=x_label,
            color="white",
            tickangle=45,
            type="date",
            tickformat=tickformat,
        ),
        yaxis=dict(title="Number of Songs", color="white"),
        font=dict(color="white"),
        showlegend=False,
    )

    fig.update_traces(
        hovertemplate=f"{x_label}: %{{x|{tickformat}}}<br>Songs: %{{y}}<extra></extra>"
    )

    return fig.to_html(full_html=False, include_plotlyjs=False)


def generate_plotly_pie_chart(genres, counts):
    """
    Generates an interactive Plotly pie chart.

    Args:
        genres (list): List of genre names.
        counts (list): Corresponding counts for each genre.

    Returns:
        str: HTML div containing the Plotly pie chart.
    """
    if not genres or not counts:
        logger.warning("Insufficient data to generate pie chart.")
        return None

    try:
        color_palette = [
            "#636EFA",
            "#EF553B",
            "#00CC96",
            "#AB63FA",
            "#FFA15A",
            "#19D3F3",
            "#FF6692",
            "#B6E880",
            "#FF97FF",
            "#FECB52",
        ]

        fig = go.Figure(
            data=[
                go.Pie(
                    labels=genres,
                    values=counts,
                    textinfo="percent+label",
                    hole=0.3,
                    marker=dict(colors=color_palette),
                )
            ]
        )

        fig.update_layout(
            plot_bgcolor="#333333", paper_bgcolor="#333333", font=dict(color="white")
        )

        graph_div = fig.to_html(full_html=False, include_plotlyjs=False)
        return graph_div
    except Exception as e:
        logger.error(f"Error generating pie chart: {e}")
        return None
