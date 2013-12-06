var nomenklatura = angular.module('nomenklatura', ['ngRoute', 'ngUpload', 'ui.bootstrap']);

nomenklatura.config(['$routeProvider', '$locationProvider', '$sceProvider',
    function($routeProvider, $locationProvider, $sceProvider) {

  $routeProvider.when('/', {
    templateUrl: '/static/templates/home.html',
    controller: HomeCtrl
  });

  $routeProvider.when('/docs/:page/:anchor', {
    templateUrl: '/static/templates/pages/template.html',
    controller: DocsCtrl
  });

  $routeProvider.when('/docs/:page', {
    templateUrl: '/static/templates/docs/template.html',
    controller: DocsCtrl
  });

  $routeProvider.when('/datasets/:name', {
    templateUrl: '/static/templates/datasets/view.html',
    controller: DatasetsViewCtrl
  });

  $routeProvider.when('/datasets/:dataset/uploads/:upload', {
    templateUrl: '/static/templates/mapping.html',
    controller: MappingCtrl
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
    redirectTo: visitPath
  });

  $locationProvider.html5Mode(true);
  //$sceProvider.enabled(false);
}]);

function visitPath(o, path) {
  window.location.reload(true);
}


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
      //console.log(status, data);
    }
  };
};
