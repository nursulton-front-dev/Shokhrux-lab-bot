import io
import datetime
import threading
from typing import List, Tuple, Dict
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

_RENDER_LOCK = threading.Lock()


def generate_weight_chart(records: List[Tuple[datetime.datetime, float]], language: str = "ru") -> Tuple[io.BytesIO, str]:
    """Render in a worker thread; serialize access to Matplotlib global state."""
    with _RENDER_LOCK, plt.style.context('dark_background'):
        return _render_weight_chart(records, language)


def _render_weight_chart(records: List[Tuple[datetime.datetime, float]], language: str) -> Tuple[io.BytesIO, str]:
    """
    Generates a weight progress chart using matplotlib.
    records: list of tuples (recorded_at, weight) sorted by date ascending.
    Returns a tuple of (BytesIO buffer containing PNG, text summary).
    """
    if not records:
        raise ValueError("No weight records provided")

    dates = [r[0] for r in records]
    weights = [r[1] for r in records]

    initial_weight = weights[0]
    latest_weight = weights[-1]
    diff = round(latest_weight - initial_weight, 2)

    if diff < 0:
        abs_diff = abs(diff)
        if language == "uz":
            summary = f"📊 <b>Natija:</b> Jami <b>{abs_diff} kg</b> vazn yo'qotildi! 🎉"
        else:
            summary = f"📊 <b>Результат:</b> Всего сброшено <b>{abs_diff} кг</b>! 🎉"
    elif diff > 0:
        if language == "uz":
            summary = f"📊 <b>Natija:</b> Jami <b>{diff} kg</b> vazn to'pland! 💪"
        else:
            summary = f"📊 <b>Результат:</b> Всего набрано <b>{diff} кг</b>! 💪"
    else:
        if language == "uz":
            summary = f"📊 <b>Natija:</b> Vazn o'zgarmadi (<b>{latest_weight} kg</b>)."
        else:
            summary = f"📊 <b>Результат:</b> Вес не изменился (<b>{latest_weight} кг</b>)."

    # Plotting setup with modern dark aesthetic
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    try:
        fig.patch.set_facecolor('#1E1E2E')
        ax.set_facecolor('#181825')

        # Line plot with gradient effect
        ax.plot(dates, weights, color='#89B4FA', linewidth=3, marker='o', markersize=7, markerfacecolor='#F38BA8', markeredgecolor='#89B4FA', markeredgewidth=2, label='Weight (kg)')
        ax.fill_between(dates, weights, alpha=0.2, color='#89B4FA')

        # Formatting axes & labels
        title_text = "Динамика изменения веса" if language == "ru" else "Vazn o'zgarishi dinamikasi"
        y_label = "Вес (кг)" if language == "ru" else "Vazn (kg)"
    
        ax.set_title(title_text, fontsize=14, fontweight='bold', color='#CDD6F4', pad=15)
        ax.set_ylabel(y_label, fontsize=11, color='#BAC2DE')
    
        # Date formatting on X-axis
        if len(dates) > 1:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))
            fig.autofmt_xdate(rotation=30)

        # Grid & styling
        ax.grid(True, linestyle='--', alpha=0.25, color='#6C7086')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#45475A')
        ax.spines['bottom'].set_color('#45475A')
        ax.tick_params(colors='#BAC2DE')

        # Add min/max annotations if multiple points
        if len(weights) > 1:
            min_w = min(weights)
            max_w = max(weights)
            ax.set_ylim(min_w - 2.0, max_w + 2.0)

        fig.tight_layout()

        # Save to BytesIO buffer
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor())
    finally:
        plt.close(fig)
    buf.seek(0)

    return buf, summary
