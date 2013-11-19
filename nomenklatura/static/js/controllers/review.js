function ReviewCtrl($scope, $routeParams, $location, $http, session) {
    $scope.dataset = {};
    $scope.entity = {};
    $scope.matches = {};

    $http.get('/api/2/datasets/' + $routeParams.dataset).then(function(res) {
        $scope.dataset = res.data;
    });

    $scope.random = $routeParams.what == 'random';

    var loadEntity = function() {
        var randomUrl = '/api/2/review/' +  $routeParams.dataset,
            entityUrl = '/api/2/entities/' +  $routeParams.what,
            url = $scope.random ? randomUrl : entityUrl;
        $http.get(url).then(function(res) {
            $scope.entity = res.data;
            var p = {
                dataset: $routeParams.dataset,
                name: $scope.entity.name,
                exclude: $scope.entity.id,
                limit: 10
            };
            $http.get('/api/2/match', {params: p}).then(function(res) {
                $scope.matches = res.data;
            });
        });
    };

    loadEntity();
}

ReviewCtrl.$inject = ['$scope', '$routeParams', '$location', '$http', 'session'];

