import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("ninthsense_onboarding_settings_tour", {
    steps: () => [
        {
            content: "The 9thSense Onboarding block is shown",
            trigger: ".o_setting_container:contains('9thSense Onboarding')",
        },
        {
            content: "Enter the wrapper address",
            trigger: ".o_field_widget[name='ninthsense_onboarding_portal_url'] input",
            run: "edit https://onboarding.example.test",
        },
        {
            content: "Enter a secret",
            trigger: ".o_field_widget[name='ninthsense_onboarding_new_secret'] input",
            run: "edit abcdefghijklmnopqrstuvwxyz0123456789",
        },
        {
            content: "Enter the validity",
            trigger: ".o_field_widget[name='ninthsense_onboarding_link_validity_days'] input",
            run: "edit 21",
        },
        {
            content: "Save",
            trigger: ".o_form_button_save",
            expectUnloadPage: true,
            run: "click",
        },
        {
            content: "After the reload the secret is reported as set",
            trigger: "span[name='ninthsense_onboarding_secret_is_set']:contains('Secret is set')",
        },
        {
            content: "The secret box is empty",
            trigger: ".o_field_widget[name='ninthsense_onboarding_new_secret'] input:not(:value('abcdefghijklmnopqrstuvwxyz0123456789'))",
            run: ({ anchor }) => {
                if (anchor.value !== "") {
                    throw new Error("The secret box must be empty after saving");
                }
            },
        },
        {
            content: "The address was kept",
            trigger: ".o_field_widget[name='ninthsense_onboarding_portal_url'] input:value('https://onboarding.example.test')",
        },
    ],
});
