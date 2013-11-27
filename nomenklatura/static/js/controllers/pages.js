function PagesCtrl($scope, $routeParams) {
    $scope.template = '/static/templates/pages/' + $routeParams.page + '.html';

    console.log($routeParams);

    $scope.active = function(path) {
        return $routeParams.page == path ? 'active' : '';
    };
}
