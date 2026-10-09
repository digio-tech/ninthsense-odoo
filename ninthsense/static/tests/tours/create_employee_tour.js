import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("ninthsense_onboarding_create_employee_tour", {
    steps: () => [
        {
            content: "Create the employee from the applicant",
            trigger: "button[name='create_employee_from_applicant']",
            run: "click",
        },
        {
            content: "The saved employee opens with the applicant's name",
            trigger: ".o_form_view .o_form_saved .o_field_widget[name='name'] input:value('Tour Employee Candidate')",
        },
        {
            content: "Open the personal information",
            trigger: ".o_notebook .nav-link:contains('Personal')",
            run: "click",
        },
        {
            content: "The private email is filled",
            trigger: ".o_field_widget[name='private_email'] input:value('tour.employee@example.test')",
        },
        {
            content: "The birthday is filled from 9thSense",
            trigger: ".o_field_widget[name='birthday'] button:contains('Nov 9, 1997')",
        },
        {
            content: "Go back to the applicant",
            trigger: ".o_breadcrumb .breadcrumb-item a:contains('Tour Employee Candidate')",
            run: "click",
        },
        {
            content: "Open the Onboarding tab",
            trigger: ".o_notebook .nav-link:contains('Onboarding')",
            run: "click",
        },
        {
            content: "Open the request",
            trigger: ".o_field_widget[name='onboarding_request_ids'] .o_data_row:contains('Completed') td.o_data_cell",
            run: "click",
        },
        {
            content: "The request is completed",
            trigger: ".o_statusbar_status button.o_arrow_button_current:contains('Completed')",
        },
        {
            content: "Open the fill report",
            trigger: ".o_notebook .nav-link:contains('Fill report')",
            run: "click",
        },
        {
            content: "The report has a Filled group",
            trigger: ".o_horizontal_separator:contains('Filled')",
        },
        {
            content: "The birthday is listed as filled",
            trigger: ".o_field_widget[name='fill_filled_ids'] .o_data_row:contains('Date of Birth')",
        },
    ],
});
