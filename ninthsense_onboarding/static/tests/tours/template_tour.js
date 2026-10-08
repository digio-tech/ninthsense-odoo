import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("ninthsense_onboarding_template_tour", {
    steps: () => [
        {
            content: "Open the Configuration menu",
            trigger: ".o_menu_sections .dropdown-toggle:contains('Configuration')",
            run: "click",
        },
        {
            content: "Open the onboarding templates",
            trigger: ".dropdown-item:contains('Onboarding Templates')",
            run: "click",
        },
        {
            content: "Open the installed template",
            trigger: ".o_list_view .o_data_row td.o_data_cell:contains('Standard Onboarding')",
            run: "click",
        },
        {
            content: "The template lists nine documents",
            trigger: ".o_field_widget[name='line_ids'] .o_data_row:nth-child(9)",
        },
        {
            content: "Edit the Aadhaar front line",
            trigger: ".o_field_widget[name='line_ids'] .o_data_row:first-child td.o_data_cell:contains('Aadhaar')",
            run: "click",
        },
        {
            content: "Untick JPG",
            trigger: ".o_field_widget[name='line_ids'] .o_selected_row .o_field_widget[name='accept_jpg'] input",
            run: "click",
        },
        {
            content: "Save",
            trigger: ".o_form_button_save",
            run: "click",
        },
        {
            content: "The template is saved",
            trigger: ".o_form_saved",
        },
        {
            content: "Back to the list",
            trigger: ".o_breadcrumb .breadcrumb-item a:contains('Onboarding Templates')",
            run: "click",
        },
        {
            content: "Create a second template",
            trigger: ".o_list_button_add",
            run: "click",
        },
        {
            content: "Name it",
            trigger: ".o_field_widget[name='name'] input",
            run: "edit Foreign National",
        },
        {
            content: "Add a document",
            trigger: ".o_field_widget[name='line_ids'] .o_field_x2many_list_row_add button",
            run: "click",
        },
        {
            content: "Pick Passport",
            trigger: ".o_field_widget[name='line_ids'] .o_selected_row .o_field_widget[name='document_type_id'] input",
            run: "edit Passport",
        },
        {
            content: "Choose it from the list",
            trigger: ".ui-autocomplete .ui-menu-item a:contains('Passport'):not(:contains('Photo'))",
            run: "click",
        },
        {
            content: "Tick PDF",
            trigger: ".o_field_widget[name='line_ids'] .o_selected_row .o_field_widget[name='accept_pdf'] input",
            run: "click",
        },
        {
            content: "Add a second document",
            trigger: ".o_field_widget[name='line_ids'] .o_field_x2many_list_row_add button",
            run: "click",
        },
        {
            content: "Pick PAN Card on the new second line",
            trigger: ".o_field_widget[name='line_ids'] .o_data_row:nth-child(2).o_selected_row .o_field_widget[name='document_type_id'] input",
            run: "edit PAN",
        },
        {
            content: "Choose it from the list",
            trigger: ".ui-autocomplete .ui-menu-item a:contains('PAN Card')",
            run: "click",
        },
        {
            content: "Tick PDF for the PAN card",
            trigger: ".o_field_widget[name='line_ids'] .o_data_row:nth-child(2).o_selected_row .o_field_widget[name='accept_pdf'] input",
            run: "click",
        },
        {
            content: "The template lists the passport and the PAN card",
            trigger: ".o_field_widget[name='line_ids'] .o_data_row:nth-child(1):contains('Passport') ~ .o_data_row:nth-child(2) .o_field_widget[name='document_type_id'] input:value('PAN Card')",
        },
        {
            content: "Open the field mapping",
            trigger: ".o_notebook .nav-link:contains('Field Mapping')",
            run: "click",
        },
        {
            content: "Add a mapping row",
            trigger: ".o_field_widget[name='mapping_ids'] .o_field_x2many_list_row_add button",
            run: "click",
        },
        {
            content: "Search the field dropdown",
            trigger: ".o_field_widget[name='mapping_ids'] .o_selected_row .o_field_widget[name='field_key'] input",
            run: "edit Passport Number",
        },
        {
            content: "Pick Passport Number",
            trigger: ".o_select_menu_item:contains('Statutory: Passport Number')",
            run: "click",
        },
        {
            content: "The field is picked and its dropdown closed",
            trigger: "body:not(:has(.o_select_menu_item)) .o_field_widget[name='mapping_ids'] .o_selected_row .o_field_widget[name='field_key'] input:value('Statutory: Passport Number')",
        },
        {
            content: "Search the source dropdown",
            trigger: ".o_field_widget[name='mapping_ids'] .o_selected_row .o_field_widget[name='source_type_id'] input",
            run: "edit Pa",
        },
        {
            content: "The template has a PAN card, but only the passport is offered, and it is picked",
            trigger: ".ui-autocomplete:not(:has(.ui-menu-item a:contains('PAN'))) .ui-menu-item a:contains('Passport')",
            run: "click",
        },
        {
            content: "Save",
            trigger: ".o_form_button_save",
            run: "click",
        },
        {
            content: "Open the field mapping of the saved template",
            trigger: ".o_form_saved .o_notebook .nav-link:contains('Field Mapping')",
            run: "click",
        },
        {
            content: "The new template is saved with its mapping row",
            trigger: ".o_form_saved .o_field_widget[name='mapping_ids'] .o_data_row:contains('Statutory: Passport Number'):contains('Passport')",
        },
    ],
});
