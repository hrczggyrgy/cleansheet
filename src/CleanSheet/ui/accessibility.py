"""Accessibility utilities for CleanSheet."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import streamlit as st


def render_skip_link() -> None:
    """Render a skip-to-main-content link for keyboard users."""
    st.markdown(
        """
        <a href="#main-content" class="skip-link" style="
            position: absolute;
            top: -40px;
            left: 0;
            background: #0072B2;
            color: white;
            padding: 8px 16px;
            z-index: 1000;
            text-decoration: none;
            font-weight: bold;
        ">
            Skip to main content
        </a>
        <style>
            .skip-link:focus {
                top: 0;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def set_page_main_content_id() -> None:
    """Add an ID to the main content area for skip links."""
    st.markdown('<div id="main-content"></div>', unsafe_allow_html=True)


def aria_live_region(message: str, politeness: str = "polite") -> None:
    """Render an ARIA live region for dynamic announcements."""
    st.markdown(
        f'<div aria-live="{politeness}" aria-atomic="true" class="sr-only">{message}</div>',
        unsafe_allow_html=True,
    )


def sr_only(text: str) -> str:
    """Wrap text in a screen-reader-only span."""
    return f'<span class="sr-only">{text}</span>'


def inject_sr_only_style() -> None:
    """Inject CSS for screen-reader-only elements."""
    st.markdown(
        """
        <style>
        .sr-only {
            position: absolute;
            width: 1px;
            height: 1px;
            padding: 0;
            margin: -1px;
            overflow: hidden;
            clip: rect(0, 0, 0, 0);
            white-space: nowrap;
            border: 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@contextmanager
def focus_trap(container_id: str) -> Iterator[None]:
    """Context manager to trap focus within a container (for modals/dialogs).
    
    Note: This is a placeholder - full implementation requires JavaScript.
    """
    yield


def announce_to_screen_reader(message: str, priority: str = "polite") -> None:
    """Announce a message to screen readers via ARIA live region."""
    st.markdown(
        f'<div id="a11y-announcer" aria-live="{priority}" aria-atomic="true" class="sr-only">{message}</div>',
        unsafe_allow_html=True,
    )


def render_focus_visible_style() -> None:
    """Inject CSS to ensure focus indicators are visible."""
    st.markdown(
        """
        <style>
        /* Ensure all interactive elements have visible focus styles */
        button:focus-visible,
        a:focus-visible,
        input:focus-visible,
        select:focus-visible,
        textarea:focus-visible,
        [role="button"]:focus-visible,
        [tabindex]:focus-visible {
            outline: 3px solid #0072B2 !important;
            outline-offset: 2px !important;
            box-shadow: 0 0 0 3px rgba(0, 114, 178, 0.4) !important;
        }
        
        /* High contrast mode support */
        @media (prefers-contrast: high) {
            button:focus-visible,
            a:focus-visible,
            input:focus-visible,
            select:focus-visible,
            textarea:focus-visible {
                outline: 3px solid #000 !important;
                outline-offset: 2px !important;
            }
        }
        
        /* Reduced motion support */
        @media (prefers-reduced-motion: reduce) {
            * {
                animation-duration: 0.01ms !important;
                animation-iteration-count: 1 !important;
                transition-duration: 0.01ms !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def accessible_button(
    label: str,
    key: str,
    help_text: str | None = None,
    disabled: bool = False,
    primary: bool = False,
    **kwargs,
) -> bool:
    """Render a button with proper accessibility attributes."""
    # Build aria attributes
    aria_attrs = {}
    if help_text:
        aria_attrs["aria-describedby"] = f"{key}-help"
    if disabled:
        aria_attrs["aria-disabled"] = "true"

    # Render button with help text
    clicked = st.button(
        label,
        key=key,
        help=help_text,
        disabled=disabled,
        type="primary" if primary else "secondary",
        **kwargs,
    )

    # Render help text with proper ID for aria-describedby
    if help_text and not disabled:
        st.markdown(
            f'<span id="{key}-help" class="sr-only">{help_text}</span>',
            unsafe_allow_html=True,
        )

    return clicked


def accessible_selectbox(
    label: str,
    options: list,
    key: str,
    help_text: str | None = None,
    disabled: bool = False,
    **kwargs,
) -> str:
    """Render a selectbox with proper accessibility attributes."""
    selected = st.selectbox(
        label,
        options,
        key=key,
        help=help_text,
        disabled=disabled,
        **kwargs,
    )

    if help_text:
        st.markdown(
            f'<span id="{key}-help" class="sr-only">{help_text}</span>',
            unsafe_allow_html=True,
        )

    return selected


def accessible_text_input(
    label: str,
    key: str,
    help_text: str | None = None,
    disabled: bool = False,
    **kwargs,
) -> str:
    """Render a text input with proper accessibility attributes."""
    value = st.text_input(
        label,
        key=key,
        help=help_text,
        disabled=disabled,
        **kwargs,
    )

    if help_text:
        st.markdown(
            f'<span id="{key}-help" class="sr-only">{help_text}</span>',
            unsafe_allow_html=True,
        )

    return value


def render_progress_with_announcement(
    label: str,
    current: int,
    total: int,
    message: str,
    key: str,
) -> None:
    """Render a progress bar with screen reader announcement."""
    progress = current / total if total > 0 else 0
    st.progress(progress, text=f"{label}: {current}/{total} - {message}")

    # Announce to screen readers
    announce_to_screen_reader(
        f"{label}: {current} of {total} complete. {message}",
        priority="polite"
    )


def ensure_keyboard_navigation() -> None:
    """Ensure proper keyboard navigation by setting tabindex and focus styles."""
    st.markdown(
        """
        <script>
        // Ensure all interactive elements are keyboard accessible
        document.addEventListener('DOMContentLoaded', function() {
            // Add tabindex to elements that should be focusable
            const interactiveElements = document.querySelectorAll(
                'button, a, input, select, textarea, [role="button"], [role="tab"], [role="menuitem"]'
            );
            
            interactiveElements.forEach(el => {
                if (!el.hasAttribute('tabindex') && !el.disabled) {
                    el.setAttribute('tabindex', '0');
                }
            });
            
            // Trap focus in modals (if any)
            const modals = document.querySelectorAll('[role="dialog"]');
            modals.forEach(modal => {
                const focusableElements = modal.querySelectorAll(
                    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
                );
                if (focusableElements.length > 0) {
                    const firstElement = focusableElements[0];
                    const lastElement = focusableElements[focusableElements.length - 1];
                    
                    modal.addEventListener('keydown', function(e) {
                        if (e.key === 'Tab') {
                            if (e.shiftKey && document.activeElement === firstElement) {
                                e.preventDefault();
                                lastElement.focus();
                            } else if (!e.shiftKey && document.activeElement === lastElement) {
                                e.preventDefault();
                                firstElement.focus();
                            }
                        }
                    });
                }
            });
        });
        </script>
        """,
        unsafe_allow_html=True,
    )


# Initialize accessibility styles on import
inject_sr_only_style()
render_focus_visible_style()
