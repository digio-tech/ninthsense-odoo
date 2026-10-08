import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("ninthsense_onboarding_send_link_tour", {
    steps: () => [
        {
            content: "Send the onboarding link",
            trigger: "button[name='action_send_onboarding_link']:contains('Send onboarding link')",
            run: "click",
        },
        {
            content: "The default template is preselected",
            trigger: ".modal .o_field_widget[name='template_id'] input:value('Standard Onboarding')",
        },
        {
            content: "Search for the other template",
            trigger: ".modal .o_field_widget[name='template_id'] input",
            run: "edit Foreign",
        },
        {
            content: "Pick it",
            trigger: ".ui-autocomplete .ui-menu-item a:contains('Foreign National')",
            run: "click",
        },
        {
            content: "Send",
            trigger: ".modal button[name='action_send']",
            run: "click",
        },
        {
            content: "The link dialog names the candidate's email",
            trigger: ".modal:contains('Onboarding link sent to tour.candidate@example.test')",
        },
        {
            content: "It shows the link with a copy button",
            trigger: ".modal .o_field_widget[name='url']:has(a[href*='/s/']):has(.o_clipboard_button)",
        },
        {
            content: "It warns that no outgoing mail server is configured",
            trigger: ".modal .alert-warning:contains('No outgoing mail server is configured')",
        },
        {
            content: "Close the dialog",
            trigger: ".modal .modal-footer button:contains('Close')",
            run: "click",
        },
        {
            content: "The form reloads and now offers a resend",
            trigger: "body:not(:has(.modal)) button[name='action_send_onboarding_link']:contains('Resend onboarding link')",
        },
        {
            content: "Open the Onboarding tab",
            trigger: ".o_notebook .nav-link:contains('Onboarding')",
            run: "click",
        },
        {
            content: "One request is listed, in Link sent, with the picked template",
            trigger: ".o_field_widget[name='onboarding_request_ids'] .o_data_row:contains('Link sent'):contains('Foreign National')",
        },
        {
            content: "Resend",
            trigger: "button[name='action_send_onboarding_link']:contains('Resend onboarding link')",
            run: "click",
        },
        {
            content: "The request's template is preselected",
            trigger: ".modal .o_field_widget[name='template_id'] input:value('Foreign National')",
        },
        {
            content: "Send again",
            trigger: ".modal button[name='action_send']",
            run: "click",
        },
        {
            content: "The link dialog opens again with the new link",
            trigger: ".modal:contains('Onboarding link sent to tour.candidate@example.test') .o_field_widget[name='url'] a[href*='/s/']",
        },
        {
            content: "Close it",
            trigger: ".modal .modal-footer button:contains('Close')",
            run: "click",
        },
        {
            content: "The dialog closes",
            trigger: "body:not(:has(.modal))",
        },
        {
            content: "Still exactly one request",
            trigger: ".o_field_widget[name='onboarding_request_ids']:has(.o_data_row:contains('Link sent')):not(:has(.o_data_row:nth-child(2)))",
        },
    ],
});
