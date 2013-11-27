var nomenklatura = angular.module('nomenklatura', ['ngRoute', 'ui.bootstrap']);

nomenklatura.config(['$routeProvider', '$locationProvider',
    function($routeProvider, $locationProvider) {

  $routeProvider.when('/', {
    templateUrl: '/static/templates/home.html',
    controller: HomeCtrl
  });

  $routeProvider.when('/profile', {
    templateUrl: '/static/templates/profile.html',
    controller: ProfileCtrl
  });

  $routeProvider.when('/docs/:page/:anchor', {
    templateUrl: '/static/templates/pages/template.html',
    controller: PagesCtrl
  });

  $routeProvider.when('/docs/:page', {
    templateUrl: '/static/templates/pages/template.html',
    controller: PagesCtrl
  });

  $routeProvider.when('/datasets/:name', {
    templateUrl: '/static/templates/datasets/view.html',
    controller: DatasetsViewCtrl
  });

  $routeProvider.when('/datasets/:dataset/review/:what', {
    templateUrl: '/static/templates/review.html',
    controller: ReviewCtrl
  });

  $routeProvider.when('/entities/:id', {
    templateUrl: '/static/templates/entities/view.html',
    controller: EntitiesViewCtrl
  });

  $routeProvider.otherwise({
    redirectTo: '/'
  });

  $locationProvider.html5Mode(false);
}]);


nomenklatura.handleFormError = function(form) {
  return function(data, status) {
    if (status == 400) {
        var errors = [];
        for (var field in data.errors) {
            form[field].$setValidity('value', false);
            form[field].$message = data.errors[field];
            errors.push(field);
        }
        if (angular.isDefined(form._errors)) {
            angular.forEach(form._errors, function(field) {
                if (errors.indexOf(field) == -1) {
                    form[field].$setValidity('value', true);
                }
            });
        }
        form._errors = errors;
    } else {
      // TODO: where is your god now?
      if (angular.isObject(data) && data.message) {
        alert(data.message);
      }
      console.log(status, data);
    }
  };
};
