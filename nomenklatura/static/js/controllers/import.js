
function UploadCtrl($scope, $routeParams, $modalInstance, $location, $http, $sce, session, dataset) {
    $scope.dataset = angular.copy(dataset);
    $scope.form_action = '/api/2';
    $scope.upload = {};

    $scope.$watch('dataset', function() {
        $scope.form_action = $sce.trustAsUrl('/api/2/datasets/' + $scope.dataset.name + '/uploads');
    });

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };

    $scope.results = function(content) {
        if (!content.parse_error) {
            $modalInstance.dismiss('cancel');
            $location.path('/datasets/' + $scope.dataset.name + '/uploads/' + content.id);
        } else {
            $scope.upload = content;
        }
    };
}

UploadCtrl.$inject = ['$scope', '$routeParams', '$modalInstance', '$location', '$http', '$sce', 'session', 'dataset'];


function MappingCtrl($scope, $routeParams, $location, $http, session) {
    var url = '/api/2/datasets/' + $routeParams.dataset + '/uploads/' + $routeParams.upload;

    $scope.errors = {};
    $scope.dataset = {};
    $scope.upload = {};
    $scope.mapping = { 'columns': {}, 'reviewed': true };

    $http.get('/api/2/datasets/' + $routeParams.dataset).then(function(res) {
        $scope.dataset = res.data;
    });

    $http.get(url).then(function(res) {
        $scope.upload = res.data;
    });

    $scope.beginImport = function() {
        var dfd = $http.post(url, $scope.mapping);
        dfd.success(function(res) {
            $location.path('/datasets/' + $scope.dataset.name);
        });
        dfd.error(function(res) {
            $scope.errors = res;
        });
    };

}

MappingCtrl.$inject = ['$scope', '$routeParams', '$location', '$http', 'session'];
