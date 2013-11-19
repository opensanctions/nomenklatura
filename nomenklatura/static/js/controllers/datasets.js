
function DatasetsViewCtrl($scope, $routeParams, $location, $http, $modal, session) {
    $scope.dataset = {};
    $scope.entities = {};

    session.authz($routeParams.name);
    
    $http.get('/api/2/datasets/' + $routeParams.name).then(function(res) {
        $scope.dataset = res.data;
    });

    var params = {dataset: $routeParams.name};
    $http.get('/api/2/entities', {params: params}).then(function(res) {
        $scope.entities = res.data;
    });

    $scope.editDataset = function(){
        var d = $modal.open({
            templateUrl: '/static/templates/datasets/edit.html',
            controller: 'DatasetsEditCtrl',
            resolve: {
                dataset: function () { return $scope.dataset; }
            }
        });
    };
}

DatasetsViewCtrl.$inject = ['$scope', '$routeParams', '$location', '$http', '$modal', 'session'];


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