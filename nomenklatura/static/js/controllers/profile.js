function ProfileCtrl($scope, $location, $modalInstance, session) {
    $scope.session = {logged_in: false};

    session.get(function(data) {
        $scope.session = data;
    });

    $scope.cancel = function() {
        $modalInstance.dismiss('cancel');
    };
    
}

ProfileCtrl.$inject = ['$scope', '$location', '$modalInstance', 'session'];