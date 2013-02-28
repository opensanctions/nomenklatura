$(function() {
  
  $saveForm = $('#save-match');
  $radios = $('#save-match input[type=radio]');

  $('#new-text').focus(function(e) {
    $('#new').prop('checked', true);
  });

  $('input').keydown(function(e) {
    if (e.which == 27) {
      $(e.target).blur();
    }
  });

  $('body').keydown(function(e) {
    if (!$('input').is(':focus')) {
      console.log(e.which);
      var selectedRadio = $radios.index($radios.filter(':checked'));

      if (e.which >= 49 && e.which <= 57) {
        $($radios.get(e.which-49)).prop('checked', true);
        $saveForm.submit();
        e.preventDefault();
      }
      switch(e.which) {
        case 13: //Enter
          $saveForm.submit();
          break;
        case 73: // 'i'
          $('#invalid').prop('checked', true);
          $saveForm.submit();
          break;
        case 78: // 'n'
          $('#new-text').focus();
          e.preventDefault();
          break;
        case 70: // 'f'
          $('#filter-field').focus();
          e.preventDefault();
          break;
        case 71:
          window.open($('#google-link').attr('href'));
          e.preventDefault();
          break;
        case 38: // up
          $($radios.get(selectedRadio-1)).prop('checked', true);
          e.preventDefault();
          break;
        case 40: // down;
          $($radios.get(selectedRadio+1)).prop('checked', true);
          e.preventDefault();
          break;
      }
    }
  });
});
