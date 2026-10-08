import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("ninthsense_onboarding_cancel_on_refuse_tour", {
    steps: () => [
        {
            content: "Refuse the applicant",
            trigger: "button[name='archive_applicant']",
            run: "click",
        },
        {
            content: "Confirm the refusal in the dialog",
            trigger: ".modal-footer button[name='action_refuse_reason_apply']",
            run: "click",
        },
        {
            content: "The applicant is refused",
            trigger: ".o_form_view .ribbon:contains('Refused')",
        },
        {
            content: "Open the Onboarding tab",
            trigger: ".o_notebook .nav-link:contains('Onboarding')",
            run: "click",
        },
        {
            content: "The request is listed as Cancelled",
            trigger: ".o_field_widget[name='onboarding_request_ids'] .o_data_row:contains('Cancelled')",
        },
        {
            content: "Open the request",
            trigger: ".o_field_widget[name='onboarding_request_ids'] .o_data_row:contains('Cancelled') td.o_data_cell",
            run: "click",
        },
        {
            content: "The request is Cancelled",
            trigger: ".o_statusbar_status button.o_arrow_button_current:contains('Cancelled')",
        },
        {
            content: "Open the details",
            trigger: ".modal .o_notebook .nav-link:contains('Details')",
            run: "click",
        },
        {
            content: "The reason is Refused",
            trigger: ".modal .o_field_widget[name='cancel_reason']:contains('Refused')",
        },
    ],
});
