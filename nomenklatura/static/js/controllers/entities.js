
function EntitiesViewCtrl($scope, $routeParams, $location, $http, $modal, $timeout, session) {
    $scope.dataset = {};
    $scope.entity = {};
    $scope.aliases = {};
    $scope.has_aliases = false;
    
    $http.get('/api/2/entities/' + $routeParams.id).then(function(res) {
        $scope.entity = res.data;
        $scope.has_attributes = Object.keys(res.data.attributes).length > 0;

        $http.get('/api/2/datasets/' + res.data.dataset).then(function(res) {
            $scope.dataset = res.data;
        });
        session.authz(res.data.dataset);
    });

    function loadAliases(url) {
        $http.get(url).then(function(res) {
            $scope.aliases = res.data;
            $scope.has_aliases = res.data.count > 0;
        });
    }

    loadAliases('/api/2/entities/' + $routeParams.id + '/aliases');
}

EntitiesViewCtrl.$inject = ['$scope', '$routeParams', '$location', '$http', '$modal', '$timeout', 'session'];
