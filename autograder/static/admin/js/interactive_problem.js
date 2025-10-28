django.jQuery(document).ready(function($) {
    var interactiveCheckbox = $('#id_interactive');
    var testcasesHelpText = $('.field-testcases_zip .help');
    
    function updateHelpText() {
        if (interactiveCheckbox.is(':checked')) {
            testcasesHelpText.html(
                '<strong>Interactive Problem:</strong> Upload a ZIP containing:<br>' +
                '• Test input files (01.txt, 02.txt, etc.)<br>' +
                '• Interactor file: interactor.py, interactor.cpp, or interactor.java<br>' +
                '• The interactor handles both query answering and answer checking<br>' +
                '• C++ and Java will be automatically compiled'
            );
            testcasesHelpText.css('color', '#0066cc');
        } else {
            testcasesHelpText.html(
                'Standard Problem: ZIP with test/ folder (inputs) and sol/ folder (expected outputs)'
            );
            testcasesHelpText.css('color', '');
        }
    }
    
    interactiveCheckbox.on('change', updateHelpText);
    updateHelpText();
});

