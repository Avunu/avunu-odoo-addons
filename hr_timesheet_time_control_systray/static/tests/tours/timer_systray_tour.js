// Copyright 2026 Avunu LLC (avu.nu)
// License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("timer_systray_tour", {
    url: "/odoo",
    steps: () => [
        {
            content: "The running timer counts up in the systray",
            // The test backdates the line by 1h30m, so matching "1:3" proves
            // the elapsed time is really computed from the start time rather
            // than merely rendered -- and leaves a ten minute window before
            // the reading rolls on to 1:40:00.
            trigger: ".o_tt_systray_toggle.o_tt_running .o_tt_elapsed:contains(1:3)",
            run: "click",
        },
        {
            content: "The dropdown says what the timer is on",
            trigger: ".o_tt_systray_menu:contains(Browser check)",
        },
        {
            content: "...and which record it belongs to",
            trigger: ".o_tt_systray_menu:contains(Shop Labor UI)",
        },
        {
            content: "Stop it",
            trigger: ".o_tt_systray_menu button:contains(Stop)",
            run: "click",
        },
        {
            content: "The systray goes quiet",
            trigger: ".o_tt_systray_toggle:not(.o_tt_running)",
        },
        {
            content: "...and offers to start the next stint",
            trigger: ".o_tt_systray_toggle",
            run: "click",
        },
        {
            content: "No timer running",
            trigger: ".o_tt_systray_menu button:contains(Start work)",
        },
    ],
});
