"""
app.py

Gradio interface for FitFindr. The layout and wiring are already set up —
your job is to fill in handle_query() so it calls run_agent() and maps
the session results to the three output panels.

Run with:
    python app.py

Then open the localhost URL shown in your terminal (usually http://localhost:7860,
but check your terminal — the port may differ).
"""

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── query handler ─────────────────────────────────────────────────────────────

def handle_query(user_query: str, wardrobe_choice: str) -> tuple[str, str, str]:
    """
    Called by Gradio when the user submits a query.

    Args:
        user_query:     The text the user typed into the search box.
        wardrobe_choice: Either "Example wardrobe" or "Empty wardrobe (new user)".

    Returns:
        A tuple of three strings:
            (listing_text, outfit_suggestion, fit_card)
        Each string maps to one of the three output panels in the UI.

    TODO:
        1. Guard against an empty query (return early with an error message).
        2. Select the wardrobe based on wardrobe_choice.
        3. Call run_agent() with the query and selected wardrobe.
        4. If session["error"] is set, return the error in the first panel
           and empty strings for the other two.
        5. Otherwise, format session["selected_item"] into a readable listing_text
           string and return it along with session["outfit_suggestion"] and
           session["fit_card"].
    """
    if not user_query or not user_query.strip():
        return "Tell FitFindr what you want to search for first.", "", ""

    wardrobe = (
        get_empty_wardrobe()
        if wardrobe_choice == "Empty wardrobe (new user)"
        else get_example_wardrobe()
    )
    session = run_agent(user_query.strip(), wardrobe)

    if session["error"]:
        retry_note = session.get("retry_note") or ""
        return "\n\n".join(part for part in [retry_note, session["error"]] if part), "", ""

    item = session["selected_item"]
    price = session.get("price_assessment") or {}
    trend = session.get("trend_signal") or {}
    memory_note = session.get("memory_note")
    retry_note = session.get("retry_note")

    listing_lines = [
        f"{item['title']}",
        f"${item['price']:.2f} on {item['platform']} - {item['condition']} condition",
        f"Size: {item['size']}",
        f"Brand: {item.get('brand') or 'unbranded'}",
        f"Tags: {', '.join(item.get('style_tags', []))}",
        f"Colors: {', '.join(item.get('colors', []))}",
    ]
    if retry_note:
        listing_lines.append(f"\nFallback: {retry_note}")
    if memory_note:
        listing_lines.append(f"\nMemory: {memory_note}")
    if price:
        listing_lines.append(
            "\nPrice check: "
            f"{price['assessment']} (${price['item_price']:.2f} vs "
            f"${price['average_comparable_price']:.2f} average across "
            f"{price['comparable_count']} comparable listings). "
            f"{price['reasoning']}"
        )
    if trend:
        listing_lines.append(
            f"\nTrend signal: {trend['trend']}. {trend['styling_note']}\nSource: {trend['source']}"
        )

    return "\n".join(listing_lines), session["outfit_suggestion"], session["fit_card"]


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",   # deliberate no-results test
]

def build_interface():
    with gr.Blocks(title="FitFindr") as demo:
        gr.Markdown("""
# FitFindr 🛍️
Find secondhand pieces and get outfit ideas based on your wardrobe.
Describe what you're looking for — include size and price if you want to filter.
        """)

        with gr.Row():
            query_input = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g. vintage graphic tee under $30, size M",
                lines=2,
                scale=3,
            )
            wardrobe_choice = gr.Radio(
                choices=["Example wardrobe", "Empty wardrobe (new user)"],
                value="Example wardrobe",
                label="Wardrobe",
                scale=1,
            )

        submit_btn = gr.Button("Find it", variant="primary")

        with gr.Row():
            listing_output = gr.Textbox(
                label="🛍️ Top listing found",
                lines=8,
                interactive=False,
            )
            outfit_output = gr.Textbox(
                label="👗 Outfit idea",
                lines=8,
                interactive=False,
            )
            fitcard_output = gr.Textbox(
                label="✨ Your fit card",
                lines=8,
                interactive=False,
            )

        gr.Examples(
            examples=[[q, "Example wardrobe"] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice],
            label="Try these queries",
        )

        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output],
        )
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output],
        )

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()
