
function UploadCtrl($scope, $routeParams, $modalInstance, $location, $http, session, dataset) {
    $scope.dataset = angular.copy(dataset);

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };

    $scope.results = function(content, completed) {
        console.log(content);
    };
}

UploadCtrl.$inject = ['$scope', '$routeParams', '$modalInstance', '$location', '$http', 'session', 'dataset'];
