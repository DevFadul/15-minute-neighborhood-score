"""Small hand-drawn inline SVG icon library, matching the app's line-icon style.

Kept as plain 24x24 viewBox line icons with no baked-in size or color so any
call site can wrap them in a container that sets both via Tailwind classes
(stroke="currentColor" picks up the wrapper's text color).
"""

from markupsafe import Markup

_ATTRS = 'viewBox="0 0 24 24" width="100%" height="100%" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"'

CATEGORY_ICONS = {
    "grocery": Markup(f"""<svg {_ATTRS}>
        <path d="M3 4h2l2.4 12.2a2 2 0 0 0 2 1.6h7.6a2 2 0 0 0 2-1.6L21 8H6.2"/>
        <circle cx="9" cy="20" r="1.2"/><circle cx="17" cy="20" r="1.2"/>
    </svg>"""),
    "healthcare": Markup(f"""<svg {_ATTRS}>
        <circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/>
    </svg>"""),
    "education": Markup(f"""<svg {_ATTRS}>
        <path d="M12 4 2 9l10 5 10-5-10-5z"/>
        <path d="M6 11.5V16c0 1.5 2.7 3 6 3s6-1.5 6-3v-4.5"/>
        <path d="M22 9v6"/>
    </svg>"""),
    "transit": Markup(f"""<svg {_ATTRS}>
        <rect x="3" y="5" width="18" height="12" rx="2"/>
        <path d="M3 12h18M7 8.5h3M14 8.5h3"/>
        <circle cx="7.5" cy="19" r="1.3"/><circle cx="16.5" cy="19" r="1.3"/>
    </svg>"""),
    "parks": Markup(f"""<svg {_ATTRS}>
        <circle cx="12" cy="9" r="6"/><path d="M12 15v6M9 21h6"/>
    </svg>"""),
    "retail": Markup(f"""<svg {_ATTRS}>
        <path d="M6 8h12l-1 12a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L6 8z"/>
        <path d="M9 8V6a3 3 0 0 1 6 0v2"/>
    </svg>"""),
}

CATEGORY_COLORS = {
    "grocery": "#b5791f",
    "healthcare": "#8a2a2a",
    "education": "#3c4f7a",
    "transit": "#1f5c52",
    "parks": "#4d6b3a",
    "retail": "#6b4a7a",
}

CATEGORY_LETTERS = {
    "grocery": "G",
    "healthcare": "H",
    "education": "E",
    "transit": "T",
    "parks": "P",
    "retail": "R",
}

CATEGORY_SHORT = {
    "grocery": "Grocery",
    "healthcare": "Healthcare",
    "education": "Education",
    "transit": "Transit",
    "parks": "Parks",
    "retail": "Retail",
}

ICON_HOME = Markup(f"""<svg {_ATTRS}>
    <path d="M4 11 12 4l8 7"/>
    <path d="M6 10v9a1 1 0 0 0 1 1h3v-5h4v5h3a1 1 0 0 0 1-1v-9"/>
</svg>""")

ICON_PIN = Markup(f"""<svg {_ATTRS}>
    <path d="M12 21s7-7.58 7-12A7 7 0 0 0 5 9c0 4.42 7 12 7 12z"/>
    <circle cx="12" cy="9" r="2.5"/>
</svg>""")
