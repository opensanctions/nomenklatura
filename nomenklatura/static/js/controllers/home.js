function HomeCtrl($scope, $location, $http, $modal) {

    $scope.loadDatasets = function(url) {
        $http.get(url).then(function(data) {
            $scope.datasets = data.data;
        });
    };
    
    $scope.loadDatasets('/api/2/datasets?limit=10');


    $scope.newDataset = function(){
        var d = $modal.open({
            templateUrl: '/static/templates/datasets/new.html',
            controller: 'DatasetsNewCtrl'
        });
    };
}

HomeCtrl.$inject = ['$scope', '$location', '$http', '$modal'];