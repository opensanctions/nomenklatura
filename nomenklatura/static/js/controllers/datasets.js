
function DatasetsViewCtrl($scope, $routeParams, $location, $http, $modal, $timeout, session) {
    $scope.dataset = {};
    $scope.entities = {};
    $scope.query = '';

    session.authz($routeParams.name);
    
    $http.get('/api/2/datasets/' + $routeParams.name).then(function(res) {
        $scope.dataset = res.data;
    });

    $scope.loadEntities = function(url, params) {
        $http.get(url, {params: params}).then(function(res) {
            $scope.entities = res.data;
        });
    };

    var params = {dataset: $routeParams.name, 'limit': 15},
        filterTimeout = null;
    $scope.loadEntities('/api/2/entities', params);
    
    $scope.updateFilter = function() {
        if (filterTimeout) { $timeout.cancel(filterTimeout); }

        filterTimeout = $timeout(function() {
            var fparams = angular.copy(params);
            fparams.filter_name = $scope.query;
            $scope.loadEntities('/api/2/entities', fparams);
        }, 500);
    };

    $scope.editDataset = function() {
        var d = $modal.open({
            templateUrl: '/static/templates/datasets/edit.html',
            controller: 'DatasetsEditCtrl',
            resolve: {
                dataset: function () { return $scope.dataset; }
            }
        });
    };
}

DatasetsViewCtrl.$inject = ['$scope', '$routeParams', '$location', '$http', '$modal', '$timeout', 'session'];


function DatasetsNewCtrl($scope, $routeParams, $modalInstance, $location, $http, session) {
    $scope.dataset = {};

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };

    $scope.create = function(form) {
        var res = $http.post('/api/2/datasets', $scope.dataset);
        res.success(function(data) {
            window.location.hash = '#/datasets/' + data.name;
            $modalInstance.dismiss('ok');
        });
        res.error(nomenklatura.handleFormError(form));
    };
}

DatasetsNewCtrl.$inject = ['$scope', '$routeParams', '$modalInstance', '$location', '$http', 'session'];


function DatasetsEditCtrl($scope, $route, $routeParams, $modalInstance, $location, $http, dataset) {
    $scope.dataset = angular.copy(dataset);

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };

    $scope.update = function(form) {
        var res = $http.post('/api/2/datasets/' + $scope.dataset.name, $scope.dataset);
        res.success(function(data) {
            $route.reload();
            $modalInstance.dismiss('ok');
        });
        res.error(nomenklatura.handleFormError(form));
    };
}

DatasetsEditCtrl.$inject = ['$scope', '$route', '$routeParams', '$modalInstance', '$location', '$http', 'dataset'];