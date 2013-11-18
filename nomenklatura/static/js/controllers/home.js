function HomeCtrl($scope, $location, $http) {
    $http.get('/api/2/datasets').then(function(data) {
        $scope.datasets = data.data.results;
    });
}

HomeCtrl.$inject = ['$scope', '$location', '$http'];