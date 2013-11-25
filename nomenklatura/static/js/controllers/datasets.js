
function DatasetsViewCtrl($scope, $routeParams, $location, $http, $modal, $timeout, session) {
    $scope.dataset = {};
    $scope.entities = {};
    $scope.new_entity = {};
    $scope.query = '';

    session.authz($routeParams.name);
    
    $http.get('/api/2/datasets/' + $routeParams.name).then(function(res) {
        $scope.dataset = res.data;

        $scope.aliases_percent = Math.ceil((res.data.stats.num_aliases / res.data.stats.num_entities)*100);
        $scope.invalid_percent = Math.ceil((res.data.stats.num_invalid / res.data.stats.num_entities)*100);
        $scope.review_percent = Math.ceil((res.data.stats.num_review / res.data.stats.num_entities)*100);
        $scope.normal_percent = 100 - $scope.aliases_percent - $scope.invalid_percent - $scope.review_percent;
        $scope.normal_num = res.data.stats.num_entities - res.data.stats.num_aliases -
            res.data.stats.num_invalid - res.data.stats.num_review;
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

    $scope.createEntity = function(form) {
        $scope.new_entity.dataset = $scope.dataset.name;
        console.log(form);
        var res = $http.post('/api/2/entities', $scope.new_entity);
        res.success(function(data) {
            window.location.hash = '#/entities/' + data.id;
        });
        res.error(nomenklatura.handleFormError(form));
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