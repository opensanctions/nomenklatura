
function EntitiesViewCtrl($scope, $routeParams, $location, $http, $modal, $timeout, session) {
    $scope.dataset = {};
    $scope.entity = {};
    
    $http.get('/api/2/entities/' + $routeParams.id).then(function(res) {
        $scope.entity = res.data;
        $http.get('/api/2/dataset/' + res.data.dataset).then(function(res) {
            $scope.dataset = res.data;
        });
        session.authz(res.data.dataset);
    });
}

EntitiesViewCtrl.$inject = ['$scope', '$routeParams', '$location', '$http', '$modal', '$timeout', 'session'];
