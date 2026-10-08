import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("ninthsense_onboarding_create_employee_edit_tour", {
    steps: () => [
        {
            content: "Create the employee from the applicant",
            trigger: "button[name='create_employee_from_applicant']",
            run: "click",
        },
        {
            content: "The saved employee opens",
            trigger: ".o_form_view .o_form_saved .o_field_widget[name='name'] input:value('Tour Edit Candidate')",
        },
        {
            content: "Open the personal information",
            trigger: ".o_notebook .nav-link:contains('Personal')",
            run: "click",
        },
        {
            content: "The city is filled from 9thSense",
            trigger: ".o_field_widget[name='private_city'] input:value('Bengaluru')",
        },
        {
            content: "Change the city",
            trigger: ".o_field_widget[name='private_city'] input",
            run: "edit Mysuru",
        },
        {
            content: "Leave the field, as HR would",
            trigger: ".o_field_widget[name='private_zip'] input",
            run: "click",
        },
        {
            content: "Save the employee",
            trigger: ".o_form_button_save",
            run: "click",
        },
        {
            content: "The employee is saved with the new city",
            trigger: ".o_form_saved .o_field_widget[name='private_city'] input:value('Mysuru')",
        },
    ],
});
