function HomeCtrl($scope, $location, $http, $modal) {
    $http.get('/api/2/datasets').then(function(data) {
        $scope.datasets = data.data.results;
    });


    $scope.newDataset = function(){
        var d = $modal.open({
            templateUrl: '/static/templates/datasets/new.html',
            controller: 'DatasetsNewCtrl'
        });
    };
}

HomeCtrl.$inject = ['$scope', '$location', '$http', '$modal'];