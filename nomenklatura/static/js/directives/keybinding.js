nomenklatura.directive('nkBindKey', ['$timeout', 'session', function ($timeout, session) {
    return {
        restrict: 'A',
        scope: {
            'nkBindKey': '@',
            'keyDo': '@'
        },
        link: function (scope, element, attrs, model) {
            var keyCode = parseInt(scope.nkBindKey, 10),
                keyDo = scope.keyDo || 'focus';
            scope.$on('key-pressed', function(e, k) {
                if (k==keyCode) {
                    element[keyDo]();
                }
            });
        }
    };
}]);